from blockchain_sandbox.engine.agentic_simulation import _rescale_hash_powers_by_group


def test_rescale_hash_powers_to_target_selfish_share():
    normalized = [0.20, 0.15, 0.10, 0.05, 0.18, 0.12, 0.11, 0.09]
    selfish_flags = [True, True, True, False, False, False, False, False]
    out = _rescale_hash_powers_by_group(
        normalized=normalized,
        selfish_flags=selfish_flags,
        target_selfish_share=0.35,
    )
    selfish_share = sum(v for v, s in zip(out, selfish_flags) if s)
    assert abs(sum(out) - 1.0) < 1e-12
    assert abs(selfish_share - 0.35) < 1e-12


def test_rescale_hash_powers_requires_matching_role_groups():
    normalized = [0.4, 0.6]
    selfish_flags = [False, False]
    try:
        _rescale_hash_powers_by_group(
            normalized=normalized,
            selfish_flags=selfish_flags,
            target_selfish_share=0.2,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "no selfish miners" in str(exc)
