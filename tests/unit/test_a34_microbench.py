"""Real mature crypto; no timer or signing substitutes."""

from experiments.agent_guard_bench.microbench import run_real_crypto_microbenchmark


def test_real_crypto_microbench_count_and_measurement_contract(tmp_path):
    path = tmp_path / "microbench.json"
    result = run_real_crypto_microbenchmark(out_path=path)
    assert path.exists()
    assert result["OpenSSL_profile_control"]["wrong_user_id"] == "REJECTED"
    assert result["OpenSSL_profile_control"]["positive_native_exit"] == 0
    assert result["model"] == "N/A" and result["chain_length"] == 3
    assert result["vectors"]["negative"] == ["REJECTED", "REJECTED"]
    assert result["vectors"]["SM2_published"] == "VERIFIED"
    for name in ("SM2sign", "SM2verify", "SM3", "chain3verify"):
        measurement = result["measurements"][name]
        assert measurement["warmup_n"] == 50 and len(measurement["warmup"]) == 50
        assert measurement["measured_n"] == 1000 and len(measurement["raw"]) == 1000
        assert measurement["latency"]["n"] == 1000
        assert all(r["end_ns"] > r["start_ns"] for r in measurement["raw"])
        assert measurement["latency"]["p99_ns"] >= measurement["latency"]["p50_ns"] > 0
