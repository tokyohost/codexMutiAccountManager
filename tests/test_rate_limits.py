from backend.services.account_service import AccountService


def test_parse_new_rate_limit_buckets() -> None:
    result = AccountService._parse_rate_limits(
        {
            "rateLimitsByLimitId": {
                "primary": {
                    "limitName": "5 hour limit",
                    "primary": {"usedPercent": 26, "windowDurationMins": 300, "resetsAt": 1700000000},
                    "secondary": {"usedPercent": 81, "windowDurationMins": 10080},
                }
            }
        }
    )
    assert len(result) == 1
    assert result[0].primary.used_percent == 26
    assert result[0].secondary is not None
    assert result[0].secondary.window_duration_mins == 10080


def test_parse_legacy_rate_limits() -> None:
    result = AccountService._parse_rate_limits(
        {"rateLimits": {"primary": {"usedPercent": 50, "windowDurationMins": 1440}}}
    )
    assert result[0].primary.used_percent == 50
