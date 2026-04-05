import asyncio
import logging
import os
import queue
import threading
from typing import Any, Dict, Optional

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from ..core.interfaces import EventTypes, IEventBus, ISimulationContext, ISimulationModule


class LiveDashboardModule(ISimulationModule):
    """
    Pluggable web dashboard module.

    Design goals:
    1) Optional module injection (caller can choose to include or not include this module).
    2) Frontend is an independent static file (modules/static/index.html).
    3) Web server lifecycle is independent from simulation event loop.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8000, queue_maxsize: int = 5000):
        self.host = host
        self.port = port
        self.ctx: Optional[ISimulationContext] = None
        self.bus: Optional[IEventBus] = None
        self.disabled_events: set = set()

        # Thread-safe queue: simulation thread -> web server thread
        self.event_queue: queue.Queue[Dict[str, Any]] = queue.Queue(maxsize=max(100, queue_maxsize))
        self.active_websockets: list[WebSocket] = []

        self._server_thread: Optional[threading.Thread] = None
        self._server_started = False
        self._broadcast_task: Optional[asyncio.Task] = None

        # FASTAPI APP SETUP
        self.app = FastAPI(title="Agentic Blockchain Sandbox Live Dashboard")
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        @self.app.get("/")
        async def root():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"message": "Dashboard backend is running, but static/index.html was not found."}

        @self.app.get("/dashboard")
        async def dashboard_home():
            index_path = os.path.join(static_dir, "index.html")
            if os.path.exists(index_path):
                return FileResponse(index_path)
            return {"message": "Dashboard backend is running, but static/index.html was not found."}

        @self.app.get("/api/health")
        async def health():
            return {"ok": True, "server": "dashboard", "host": self.host, "port": self.port}

        @self.app.get("/summary")
        async def summary_page():
            summary_path = os.path.join(static_dir, "summary.html")
            if os.path.exists(summary_path):
                return FileResponse(summary_path)
            return {"message": "Summary page not found."}

        @self.app.get("/api/summary_data")
        async def get_summary_data():
            if not self.ctx:
                return {}

            try:
                # The correct way to get canonical head block and total blocks from context
                canonical_head_id = self.ctx.get_canonical_head()
                canonical_head = self.ctx.blocks.get(canonical_head_id)
                main_chain_len = canonical_head.height if canonical_head else 0
                
                # Fetch hot blocks + summaries count for accurate totals
                total_blocks = len(self.ctx.block_storage.get_all_summaries()) - 1 # exclude genesis
                total_blocks = max(0, total_blocks)
                orphan_rate = (total_blocks - main_chain_len) / max(1, total_blocks)

                miner_blocks = {}
                for b_id, summary in self.ctx.block_storage.get_all_summaries().items():
                    if b_id == self.ctx.genesis_id:
                        continue
                    m_id = summary.miner_id
                    miner_blocks[m_id] = miner_blocks.get(m_id, 0) + 1

                banned_nodes = sum(1 for n in self.ctx.nodes.values() if getattr(n, "is_banned", False))

                return {
                    "main_chain_len": main_chain_len,
                    "total_blocks": total_blocks,
                    "orphan_rate": orphan_rate,
                    "miner_blocks": miner_blocks,
                    "banned_nodes": banned_nodes,
                    "total_steps": self.ctx.current_step
                }
            except Exception as e:
                logging.error(f"Error generating summary data: {e}")
                return {"error": str(e)}

        @self.app.get("/api/topology")
        async def get_topology():
            if not self.ctx:
                return {"nodes": [], "edges": []}

            nodes_data = []
            for n_id, n_obj in self.ctx.nodes.items():
                nodes_data.append(
                    {
                        "id": n_id,
                        "is_miner": n_obj.is_miner,
                        "hash_power": n_obj.hash_power,
                        "strategy": n_obj.strategy_name,
                        "is_banned": getattr(n_obj, "is_banned", False),
                    }
                )

            edges_data = []
            for src_id in self.ctx.graph.nodes():
                for edge in self.ctx.graph.neighbors(src_id):
                    edges_data.append(
                        {
                            "source": edge.src,
                            "target": edge.dst,
                            "latency": edge.latency,
                            "reliability": edge.reliability,
                        }
                    )

            return {"nodes": nodes_data, "edges": edges_data}

        @self.app.websocket("/ws/events")
        async def websocket_endpoint(websocket: WebSocket):
            await websocket.accept()
            self.active_websockets.append(websocket)
            logging.info(f"[Live Dashboard] WebSocket connected: {websocket.client}")
            try:
                # Send an immediate handshake event so frontend can confirm pipeline is alive.
                await websocket.send_json(
                    {
                        "type": "DASHBOARD_CONNECTED",
                        "time": 0.0,
                        "step": 0,
                        "data": {"message": "WebSocket connected"},
                    }
                )

                while True:
                    # Keep-alive receive loop; actual pushes happen in _broadcast_loop().
                    # Frontend may periodically send ping text to avoid idle disconnects.
                    await websocket.receive_text()
            except WebSocketDisconnect:
                logging.info(f"[Live Dashboard] WebSocket disconnected: {websocket.client}")
                if websocket in self.active_websockets:
                    self.active_websockets.remove(websocket)
            except Exception as e:
                logging.error(f"WebSocket error: {e}")
                if websocket in self.active_websockets:
                    self.active_websockets.remove(websocket)

        @self.app.on_event("startup")
        async def _on_startup():
            if self._broadcast_task is None or self._broadcast_task.done():
                self._broadcast_task = asyncio.create_task(self._broadcast_loop())

        @self.app.on_event("shutdown")
        async def _on_shutdown():
            if self._broadcast_task and not self._broadcast_task.done():
                self._broadcast_task.cancel()

    def _start_server_thread(self) -> None:
        if self._server_started:
            return

        # Explicitly check if the port is already bound to avoid the dreaded [Errno 10048]
        import socket
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind((self.host, self.port))
        except OSError as e:
            print(f"\n[Live Dashboard] ⚠️ WARNING: Port {self.port} on {self.host} is already in use!")
            print(f"[Live Dashboard] ⚠️ The backend server cannot start. Please close the previous process or specify a different port.")
            print(f"[Live Dashboard] ⚠️ You can use `python -m experiments.run_live_dashboard --port <NEW_PORT>`\n")
            return # Give up silently without crashing the simulation

        def _run() -> None:
            config = uvicorn.Config(
                app=self.app,
                host=self.host,
                port=self.port,
                log_level="info",
                lifespan="on",
            )
            server = uvicorn.Server(config)
            server.run()

        self._server_thread = threading.Thread(target=_run, name="live-dashboard-server", daemon=True)
        self._server_thread.start()
        self._server_started = True

        print(f"\n[Live Dashboard] 🚀 Server started at http://{self.host}:{self.port}")
        print(f"[Live Dashboard] 📊 Dashboard page: http://{self.host}:{self.port}/")
        print(f"[Live Dashboard] 📡 WebSocket endpoint at ws://{self.host}:{self.port}/ws/events\n")

    def setup(self, ctx: ISimulationContext, bus: IEventBus) -> None:
        self.ctx = ctx
        self.bus = bus

        bus.subscribe(EventTypes.BLOCK_MINED, self._on_block_mined)
        bus.subscribe(EventTypes.BLOCK_RECEIVED, self._on_block_received)
        bus.subscribe(EventTypes.AGENT_DECISION_MADE, self._on_agent_decision)
        bus.subscribe(EventTypes.NODE_BANNED, self._on_node_banned)
        bus.subscribe(EventTypes.SIMULATION_END, self._on_simulation_end)

        # Start web server once, independent from simulation loop.
        self._start_server_thread()

    async def _broadcast_loop(self):
        while True:
            try:
                try:
                    event_data = self.event_queue.get_nowait()
                except queue.Empty:
                    await asyncio.sleep(0.05)
                    continue

                if not self.active_websockets:
                    continue

                dead_sockets: list[WebSocket] = []
                for ws in self.active_websockets:
                    try:
                        await ws.send_json(event_data)
                    except Exception:
                        dead_sockets.append(ws)

                for ws in dead_sockets:
                    if ws in self.active_websockets:
                        self.active_websockets.remove(ws)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.error(f"Error in broadcast loop: {e}")

    def _push_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if not self.ctx:
            return
            
        if event_type in self.disabled_events:
            return

        event = {
            "type": event_type,
            "time": self.ctx.current_time,
            "step": self.ctx.current_step,
            "data": payload,
        }
        try:
            self.event_queue.put_nowait(event)
        except queue.Full:
            # Drop oldest-ish behavior by discarding current event when overloaded.
            pass

    def _on_block_mined(self, payload: Dict[str, Any]) -> None:
        block = payload.get("block")
        if block:
            self._push_event(
                "BLOCK_MINED",
                {
                    "block_id": block.block_id,
                    "parent_id": block.parent_id,
                    "height": block.height,
                    "miner_id": block.miner_id,
                    "created_at_step": block.created_at_step,
                },
            )

    def _on_block_received(self, payload: Dict[str, Any]) -> None:
        self._push_event(
            "BLOCK_RECEIVED",
            {
                "node_id": payload.get("node_id"),
                "block_id": payload.get("block_id"),
                "hops": payload.get("hops", 0),
                "changed_head": payload.get("changed_head", False),
            },
        )

    def _on_agent_decision(self, payload: Dict[str, Any]) -> None:
        miner_id = payload.get("miner_id")
        effective = payload.get("effective")
        if not miner_id or not effective:
            return

        action = getattr(effective, "action", "")
        if action == "jam_target":
            self._push_event(
                "NETWORK_ATTACK",
                {
                    "attacker_id": miner_id,
                    "target_id": getattr(effective, "target_miner", ""),
                    "jam_steps": getattr(effective, "jam_steps", 2),
                },
            )

        social_action = getattr(effective, "social_action", "none")
        if social_action != "none":
            self._push_event(
                "FORUM_POST",
                {
                    "author_id": miner_id,
                    "action": social_action,
                    "target_id": getattr(effective, "social_target", ""),
                    "tone": getattr(effective, "social_tone", 0.0),
                    "board": getattr(effective, "social_board", "mining"),
                    "content": getattr(effective, "social_content", getattr(effective, "reason", "")),
                },
            )

    def _on_node_banned(self, payload: Dict[str, Any]) -> None:
        self._push_event(
            "NODE_BANNED",
            {
                "node_id": payload.get("node_id"),
                "reason": payload.get("reason", ""),
            },
        )

    def _on_simulation_end(self, payload: Any) -> None:
        self._push_event("SIMULATION_END", {})

    # --- REQUIRED ISimulationModule METHODS ---
    def on_step_start(self, ctx: ISimulationContext) -> None:
        return

    def augment_agent_observation(self, miner_id: str, ctx: ISimulationContext) -> Dict[str, Any]:
        return {}

    def augment_system_prompt(self, miner_id: str, ctx: ISimulationContext) -> str:
        return ""

    def expected_decision_keys(self) -> Dict[str, str]:
        return {}
