window.PRESCORE_DATA = {
  "generated_at": "2026-09-07T05:07:08Z",
  "league": "English Premier League",
  "league_code": "EPL",
  "model_version": "poisson-dc-1.3",
  "model_versions": [
    {
      "version": "poisson-dc-1.0",
      "published": 10,
      "graded": 10,
      "first_published": "2026-08-11T21:56:01Z"
    },
    {
      "version": "poisson-dc-1.1",
      "published": 10,
      "graded": 10,
      "first_published": "2026-08-12T07:10:29Z"
    },
    {
      "version": "poisson-dc-1.2",
      "published": 30,
      "graded": 30,
      "first_published": "2026-08-12T09:43:27Z"
    },
    {
      "version": "poisson-dc-1.3",
      "published": 12,
      "graded": 3,
      "first_published": "2026-09-05T16:15:36Z"
    }
  ],
  "disclaimer": "Statistical predictions and probabilities for informational purposes. Not betting advice.",
  "accuracy": {
    "overall": {
      "label": "published",
      "n": 3,
      "hits": 0,
      "misses": 3,
      "accuracy": 0.0,
      "accuracy_only": false,
      "log_loss": 1.3804589696146616,
      "rps": 0.18096873130660454,
      "brier": 0.9214817703784876,
      "by_pick": {
        "A": {
          "n": 1,
          "hits": 0,
          "accuracy": 0.0
        },
        "H": {
          "n": 2,
          "hits": 0,
          "accuracy": 0.0
        }
      }
    },
    "by_confidence": [
      {
        "range": "0.40-0.50",
        "n": 1,
        "accuracy": 0.0,
        "hits": 0
      },
      {
        "range": "0.60-0.70",
        "n": 2,
        "accuracy": 0.0,
        "hits": 0
      }
    ],
    "model_version": "poisson-dc-1.3"
  },
  "accuracy_by_version": {
    "poisson-dc-1.0": {
      "overall": {
        "label": "published",
        "n": 10,
        "hits": 6,
        "misses": 4,
        "accuracy": 0.6,
        "accuracy_only": false,
        "log_loss": 0.9405145198939385,
        "rps": 0.2428976261614328,
        "brier": 0.5534004895872069,
        "by_pick": {
          "A": {
            "n": 4,
            "hits": 1,
            "accuracy": 0.25
          },
          "H": {
            "n": 6,
            "hits": 5,
            "accuracy": 0.8333333333333334
          }
        }
      },
      "by_confidence": [
        {
          "range": "0.00-0.40",
          "n": 2,
          "accuracy": 0.5,
          "hits": 1
        },
        {
          "range": "0.40-0.50",
          "n": 5,
          "accuracy": 0.6,
          "hits": 3
        },
        {
          "range": "0.50-0.60",
          "n": 1,
          "accuracy": 0.0,
          "hits": 0
        },
        {
          "range": "0.60-0.70",
          "n": 1,
          "accuracy": 1.0,
          "hits": 1
        },
        {
          "range": "0.70-1.00",
          "n": 1,
          "accuracy": 1.0,
          "hits": 1
        }
      ],
      "model_version": "poisson-dc-1.0"
    },
    "poisson-dc-1.1": {
      "overall": {
        "label": "published",
        "n": 10,
        "hits": 6,
        "misses": 4,
        "accuracy": 0.6,
        "accuracy_only": false,
        "log_loss": 0.9293558388320602,
        "rps": 0.24081771579487268,
        "brier": 0.5475179160653025,
        "by_pick": {
          "A": {
            "n": 4,
            "hits": 1,
            "accuracy": 0.25
          },
          "H": {
            "n": 6,
            "hits": 5,
            "accuracy": 0.8333333333333334
          }
        }
      },
      "by_confidence": [
        {
          "range": "0.00-0.40",
          "n": 2,
          "accuracy": 0.5,
          "hits": 1
        },
        {
          "range": "0.40-0.50",
          "n": 5,
          "accuracy": 0.6,
          "hits": 3
        },
        {
          "range": "0.50-0.60",
          "n": 1,
          "accuracy": 0.0,
          "hits": 0
        },
        {
          "range": "0.60-0.70",
          "n": 1,
          "accuracy": 1.0,
          "hits": 1
        },
        {
          "range": "0.70-1.00",
          "n": 1,
          "accuracy": 1.0,
          "hits": 1
        }
      ],
      "model_version": "poisson-dc-1.1"
    },
    "poisson-dc-1.2": {
      "overall": {
        "label": "published",
        "n": 30,
        "hits": 14,
        "misses": 16,
        "accuracy": 0.4666666666666667,
        "accuracy_only": false,
        "log_loss": 1.026379573063243,
        "rps": 0.19045118227194532,
        "brier": 0.6247690102608671,
        "by_pick": {
          "A": {
            "n": 10,
            "hits": 6,
            "accuracy": 0.6
          },
          "H": {
            "n": 20,
            "hits": 8,
            "accuracy": 0.4
          }
        }
      },
      "by_confidence": [
        {
          "range": "0.00-0.40",
          "n": 8,
          "accuracy": 0.625,
          "hits": 5
        },
        {
          "range": "0.40-0.50",
          "n": 10,
          "accuracy": 0.2,
          "hits": 2
        },
        {
          "range": "0.50-0.60",
          "n": 5,
          "accuracy": 0.4,
          "hits": 2
        },
        {
          "range": "0.60-0.70",
          "n": 3,
          "accuracy": 0.6666666666666666,
          "hits": 2
        },
        {
          "range": "0.70-1.00",
          "n": 4,
          "accuracy": 0.75,
          "hits": 3
        }
      ],
      "model_version": "poisson-dc-1.2"
    },
    "poisson-dc-1.3": {
      "overall": {
        "label": "published",
        "n": 3,
        "hits": 0,
        "misses": 3,
        "accuracy": 0.0,
        "accuracy_only": false,
        "log_loss": 1.3804589696146616,
        "rps": 0.18096873130660454,
        "brier": 0.9214817703784876,
        "by_pick": {
          "A": {
            "n": 1,
            "hits": 0,
            "accuracy": 0.0
          },
          "H": {
            "n": 2,
            "hits": 0,
            "accuracy": 0.0
          }
        }
      },
      "by_confidence": [
        {
          "range": "0.40-0.50",
          "n": 1,
          "accuracy": 0.0,
          "hits": 0
        },
        {
          "range": "0.60-0.70",
          "n": 2,
          "accuracy": 0.0,
          "hits": 0
        }
      ],
      "model_version": "poisson-dc-1.3"
    }
  },
  "backtest": null,
  "upcoming": [
    {
      "match_id": 4216,
      "kickoff_utc": "2026-09-12T14:00:00Z",
      "round": 4,
      "home": "Aston Villa",
      "away": "Nott'm Forest",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.4356,
          "p_draw": 0.2728,
          "p_away": 0.2916,
          "pick": "H",
          "confidence": 0.4356,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4215,
      "kickoff_utc": "2026-09-12T14:00:00Z",
      "round": 4,
      "home": "Crystal Palace",
      "away": "Ipswich",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.638,
          "p_draw": 0.2077,
          "p_away": 0.1543,
          "pick": "H",
          "confidence": 0.638,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4214,
      "kickoff_utc": "2026-09-12T14:00:00Z",
      "round": 4,
      "home": "Chelsea",
      "away": "Hull",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.2221,
          "p_draw": 0.3022,
          "p_away": 0.4757,
          "pick": "A",
          "confidence": 0.4757,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4212,
      "kickoff_utc": "2026-09-12T14:00:00Z",
      "round": 4,
      "home": "Liverpool",
      "away": "Fulham",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.5899,
          "p_draw": 0.2245,
          "p_away": 0.1856,
          "pick": "H",
          "confidence": 0.5899,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4211,
      "kickoff_utc": "2026-09-12T14:00:00Z",
      "round": 4,
      "home": "Bournemouth",
      "away": "Brentford",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.4553,
          "p_draw": 0.2564,
          "p_away": 0.2883,
          "pick": "H",
          "confidence": 0.4553,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4213,
      "kickoff_utc": "2026-09-12T16:30:00Z",
      "round": 4,
      "home": "Tottenham",
      "away": "Everton",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.3818,
          "p_draw": 0.2892,
          "p_away": 0.3291,
          "pick": "H",
          "confidence": 0.3818,
          "predicted_at": "2026-09-06T08:35:16Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4217,
      "kickoff_utc": "2026-09-12T19:00:00Z",
      "round": 4,
      "home": "Sunderland",
      "away": "Arsenal",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.1444,
          "p_draw": 0.2808,
          "p_away": 0.5748,
          "pick": "A",
          "confidence": 0.5748,
          "predicted_at": "2026-09-06T08:35:16Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4219,
      "kickoff_utc": "2026-09-13T13:00:00Z",
      "round": 4,
      "home": "Coventry",
      "away": "Brighton",
      "thin_history": [
        "Coventry"
      ],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.1328,
          "p_draw": 0.2779,
          "p_away": 0.5893,
          "pick": "A",
          "confidence": 0.5893,
          "predicted_at": "2026-09-06T16:15:21Z",
          "is_hit": null
        }
      ]
    },
    {
      "match_id": 4218,
      "kickoff_utc": "2026-09-13T15:30:00Z",
      "round": 4,
      "home": "Man United",
      "away": "Man City",
      "thin_history": [],
      "graded": false,
      "home_goals": null,
      "away_goals": null,
      "actual": null,
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.2776,
          "p_draw": 0.247,
          "p_away": 0.4754,
          "pick": "A",
          "confidence": 0.4754,
          "predicted_at": "2026-09-06T16:15:21Z",
          "is_hit": null
        }
      ]
    }
  ],
  "results": [
    {
      "match_id": 4209,
      "kickoff_utc": "2026-09-06T15:30:00Z",
      "round": 3,
      "home": "Arsenal",
      "away": "Chelsea",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 1,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.635,
          "p_draw": 0.2258,
          "p_away": 0.1392,
          "pick": "H",
          "confidence": 0.635,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.605,
          "p_draw": 0.2362,
          "p_away": 0.1588,
          "pick": "H",
          "confidence": 0.605,
          "predicted_at": "2026-08-30T16:15:28Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4210,
      "kickoff_utc": "2026-09-06T13:00:00Z",
      "round": 3,
      "home": "Everton",
      "away": "Man United",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 2,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.3235,
          "p_draw": 0.2714,
          "p_away": 0.4052,
          "pick": "A",
          "confidence": 0.4052,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3349,
          "p_draw": 0.2821,
          "p_away": 0.383,
          "pick": "A",
          "confidence": 0.383,
          "predicted_at": "2026-08-30T16:15:28Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4207,
      "kickoff_utc": "2026-09-05T16:30:00Z",
      "round": 3,
      "home": "Hull",
      "away": "Aston Villa",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 0,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.3",
          "is_current": true,
          "p_home": 0.6155,
          "p_draw": 0.2595,
          "p_away": 0.1251,
          "pick": "H",
          "confidence": 0.6155,
          "predicted_at": "2026-09-05T16:15:36Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.5741,
          "p_draw": 0.2771,
          "p_away": 0.1488,
          "pick": "H",
          "confidence": 0.5741,
          "predicted_at": "2026-08-29T22:15:13Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4208,
      "kickoff_utc": "2026-09-05T14:00:00Z",
      "round": 3,
      "home": "Nott'm Forest",
      "away": "Tottenham",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 0,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4464,
          "p_draw": 0.2681,
          "p_away": 0.2855,
          "pick": "H",
          "confidence": 0.4464,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4206,
      "kickoff_utc": "2026-09-05T14:00:00Z",
      "round": 3,
      "home": "Brentford",
      "away": "Sunderland",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 1,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4854,
          "p_draw": 0.2759,
          "p_away": 0.2387,
          "pick": "H",
          "confidence": 0.4854,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4205,
      "kickoff_utc": "2026-09-05T14:00:00Z",
      "round": 3,
      "home": "Brighton",
      "away": "Leeds",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 1,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.5039,
          "p_draw": 0.2625,
          "p_away": 0.2336,
          "pick": "H",
          "confidence": 0.5039,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4204,
      "kickoff_utc": "2026-09-05T14:00:00Z",
      "round": 3,
      "home": "Man City",
      "away": "Coventry",
      "thin_history": [
        "Coventry"
      ],
      "graded": true,
      "home_goals": 1,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.8298,
          "p_draw": 0.1289,
          "p_away": 0.0413,
          "pick": "H",
          "confidence": 0.8298,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4203,
      "kickoff_utc": "2026-09-05T14:00:00Z",
      "round": 3,
      "home": "Fulham",
      "away": "Crystal Palace",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 3,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.438,
          "p_draw": 0.2832,
          "p_away": 0.2788,
          "pick": "H",
          "confidence": 0.438,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4202,
      "kickoff_utc": "2026-09-05T11:30:00Z",
      "round": 3,
      "home": "Newcastle",
      "away": "Bournemouth",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 2,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4327,
          "p_draw": 0.2549,
          "p_away": 0.3124,
          "pick": "H",
          "confidence": 0.4327,
          "predicted_at": "2026-08-29T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4201,
      "kickoff_utc": "2026-09-04T19:00:00Z",
      "round": 3,
      "home": "Ipswich",
      "away": "Liverpool",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 2,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.168,
          "p_draw": 0.2049,
          "p_away": 0.6271,
          "pick": "A",
          "confidence": 0.6271,
          "predicted_at": "2026-08-29T03:17:52Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4200,
      "kickoff_utc": "2026-08-31T19:00:00Z",
      "round": 2,
      "home": "Aston Villa",
      "away": "Arsenal",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 1,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.2082,
          "p_draw": 0.2666,
          "p_away": 0.5252,
          "pick": "A",
          "confidence": 0.5252,
          "predicted_at": "2026-08-25T03:23:40Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4196,
      "kickoff_utc": "2026-08-30T15:30:00Z",
      "round": 2,
      "home": "Man United",
      "away": "Ipswich",
      "thin_history": [],
      "graded": true,
      "home_goals": 5,
      "away_goals": 2,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.7138,
          "p_draw": 0.1731,
          "p_away": 0.1131,
          "pick": "H",
          "confidence": 0.7138,
          "predicted_at": "2026-08-23T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4199,
      "kickoff_utc": "2026-08-30T13:00:00Z",
      "round": 2,
      "home": "Sunderland",
      "away": "Fulham",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3544,
          "p_draw": 0.3031,
          "p_away": 0.3426,
          "pick": "H",
          "confidence": 0.3544,
          "predicted_at": "2026-08-23T16:15:22Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4198,
      "kickoff_utc": "2026-08-30T13:00:00Z",
      "round": 2,
      "home": "Leeds",
      "away": "Brentford",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 1,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3955,
          "p_draw": 0.2724,
          "p_away": 0.3321,
          "pick": "H",
          "confidence": 0.3955,
          "predicted_at": "2026-08-23T16:15:22Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4197,
      "kickoff_utc": "2026-08-30T13:00:00Z",
      "round": 2,
      "home": "Chelsea",
      "away": "Brighton",
      "thin_history": [],
      "graded": true,
      "home_goals": 4,
      "away_goals": 3,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3996,
          "p_draw": 0.2637,
          "p_away": 0.3367,
          "pick": "H",
          "confidence": 0.3996,
          "predicted_at": "2026-08-23T16:15:22Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4194,
      "kickoff_utc": "2026-08-29T16:30:00Z",
      "round": 2,
      "home": "Tottenham",
      "away": "Newcastle",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 2,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3675,
          "p_draw": 0.2562,
          "p_away": 0.3764,
          "pick": "A",
          "confidence": 0.3764,
          "predicted_at": "2026-08-23T04:18:20Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4195,
      "kickoff_utc": "2026-08-29T14:00:00Z",
      "round": 2,
      "home": "Coventry",
      "away": "Hull",
      "thin_history": [
        "Coventry"
      ],
      "graded": true,
      "home_goals": 0,
      "away_goals": 1,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.0937,
          "p_draw": 0.1996,
          "p_away": 0.7067,
          "pick": "A",
          "confidence": 0.7067,
          "predicted_at": "2026-08-22T16:15:18Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4192,
      "kickoff_utc": "2026-08-29T14:00:00Z",
      "round": 2,
      "home": "Bournemouth",
      "away": "Everton",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 1,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4603,
          "p_draw": 0.2722,
          "p_away": 0.2676,
          "pick": "H",
          "confidence": 0.4603,
          "predicted_at": "2026-08-22T16:15:18Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4193,
      "kickoff_utc": "2026-08-29T11:30:00Z",
      "round": 2,
      "home": "Liverpool",
      "away": "Nott'm Forest",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 2,
      "actual": "D",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.543,
          "p_draw": 0.2409,
          "p_away": 0.2161,
          "pick": "H",
          "confidence": 0.543,
          "predicted_at": "2026-08-22T16:15:18Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4191,
      "kickoff_utc": "2026-08-28T19:00:00Z",
      "round": 2,
      "home": "Crystal Palace",
      "away": "Man City",
      "thin_history": [],
      "graded": true,
      "home_goals": 1,
      "away_goals": 4,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.2048,
          "p_draw": 0.2588,
          "p_away": 0.5364,
          "pick": "A",
          "confidence": 0.5364,
          "predicted_at": "2026-08-21T22:15:19Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4190,
      "kickoff_utc": "2026-08-24T19:00:00Z",
      "round": 1,
      "home": "Fulham",
      "away": "Chelsea",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 3,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3562,
          "p_draw": 0.2816,
          "p_away": 0.3622,
          "pick": "A",
          "confidence": 0.3622,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.3566,
          "p_draw": 0.2825,
          "p_away": 0.3609,
          "pick": "A",
          "confidence": 0.3609,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.3566,
          "p_draw": 0.2825,
          "p_away": 0.3609,
          "pick": "A",
          "confidence": 0.3609,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4189,
      "kickoff_utc": "2026-08-23T15:30:00Z",
      "round": 1,
      "home": "Newcastle",
      "away": "Liverpool",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 2,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3558,
          "p_draw": 0.2494,
          "p_away": 0.3948,
          "pick": "A",
          "confidence": 0.3948,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.3575,
          "p_draw": 0.2478,
          "p_away": 0.3947,
          "pick": "A",
          "confidence": 0.3947,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.3575,
          "p_draw": 0.2478,
          "p_away": 0.3947,
          "pick": "A",
          "confidence": 0.3947,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4188,
      "kickoff_utc": "2026-08-23T13:00:00Z",
      "round": 1,
      "home": "Brighton",
      "away": "Aston Villa",
      "thin_history": [],
      "graded": true,
      "home_goals": 4,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4423,
          "p_draw": 0.2643,
          "p_away": 0.2935,
          "pick": "H",
          "confidence": 0.4423,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.4059,
          "p_draw": 0.272,
          "p_away": 0.3221,
          "pick": "H",
          "confidence": 0.4059,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.4059,
          "p_draw": 0.272,
          "p_away": 0.3221,
          "pick": "H",
          "confidence": 0.4059,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4187,
      "kickoff_utc": "2026-08-23T13:00:00Z",
      "round": 1,
      "home": "Man City",
      "away": "Bournemouth",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 1,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.6069,
          "p_draw": 0.2244,
          "p_away": 0.1687,
          "pick": "H",
          "confidence": 0.6069,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.6397,
          "p_draw": 0.2152,
          "p_away": 0.1451,
          "pick": "H",
          "confidence": 0.6397,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.6397,
          "p_draw": 0.2152,
          "p_away": 0.1451,
          "pick": "H",
          "confidence": 0.6397,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4186,
      "kickoff_utc": "2026-08-22T16:30:00Z",
      "round": 1,
      "home": "Brentford",
      "away": "Tottenham",
      "thin_history": [],
      "graded": true,
      "home_goals": 3,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.435,
          "p_draw": 0.261,
          "p_away": 0.3039,
          "pick": "H",
          "confidence": 0.435,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.4994,
          "p_draw": 0.247,
          "p_away": 0.2536,
          "pick": "H",
          "confidence": 0.4994,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.4994,
          "p_draw": 0.247,
          "p_away": 0.2536,
          "pick": "H",
          "confidence": 0.4994,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4185,
      "kickoff_utc": "2026-08-22T14:00:00Z",
      "round": 1,
      "home": "Nott'm Forest",
      "away": "Leeds",
      "thin_history": [],
      "graded": true,
      "home_goals": 0,
      "away_goals": 1,
      "actual": "A",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.4361,
          "p_draw": 0.2777,
          "p_away": 0.2863,
          "pick": "H",
          "confidence": 0.4361,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.4546,
          "p_draw": 0.2768,
          "p_away": 0.2686,
          "pick": "H",
          "confidence": 0.4546,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.4546,
          "p_draw": 0.2768,
          "p_away": 0.2686,
          "pick": "H",
          "confidence": 0.4546,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4184,
      "kickoff_utc": "2026-08-22T14:00:00Z",
      "round": 1,
      "home": "Ipswich",
      "away": "Sunderland",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 1,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.2527,
          "p_draw": 0.2841,
          "p_away": 0.4632,
          "pick": "A",
          "confidence": 0.4632,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.2033,
          "p_draw": 0.2709,
          "p_away": 0.5258,
          "pick": "A",
          "confidence": 0.5258,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.2035,
          "p_draw": 0.271,
          "p_away": 0.5255,
          "pick": "A",
          "confidence": 0.5255,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4183,
      "kickoff_utc": "2026-08-22T14:00:00Z",
      "round": 1,
      "home": "Everton",
      "away": "Crystal Palace",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.3978,
          "p_draw": 0.2979,
          "p_away": 0.3044,
          "pick": "H",
          "confidence": 0.3978,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.4131,
          "p_draw": 0.3077,
          "p_away": 0.2791,
          "pick": "H",
          "confidence": 0.4131,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.4131,
          "p_draw": 0.3077,
          "p_away": 0.2791,
          "pick": "H",
          "confidence": 0.4131,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    },
    {
      "match_id": 4182,
      "kickoff_utc": "2026-08-22T11:30:00Z",
      "round": 1,
      "home": "Hull",
      "away": "Man United",
      "thin_history": [],
      "graded": true,
      "home_goals": 2,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.2912,
          "p_draw": 0.2606,
          "p_away": 0.4482,
          "pick": "A",
          "confidence": 0.4482,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.3012,
          "p_draw": 0.2654,
          "p_away": 0.4335,
          "pick": "A",
          "confidence": 0.4335,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": false
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.3063,
          "p_draw": 0.2653,
          "p_away": 0.4284,
          "pick": "A",
          "confidence": 0.4284,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": false
        }
      ]
    },
    {
      "match_id": 4181,
      "kickoff_utc": "2026-08-21T19:00:00Z",
      "round": 1,
      "home": "Arsenal",
      "away": "Coventry",
      "thin_history": [
        "Coventry"
      ],
      "graded": true,
      "home_goals": 3,
      "away_goals": 0,
      "actual": "H",
      "predictions": [
        {
          "model_version": "poisson-dc-1.2",
          "is_current": false,
          "p_home": 0.7735,
          "p_draw": 0.169,
          "p_away": 0.0575,
          "pick": "H",
          "confidence": 0.7735,
          "predicted_at": "2026-08-12T09:43:27Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.1",
          "is_current": false,
          "p_home": 0.8096,
          "p_draw": 0.1455,
          "p_away": 0.0449,
          "pick": "H",
          "confidence": 0.8096,
          "predicted_at": "2026-08-12T07:10:29Z",
          "is_hit": true
        },
        {
          "model_version": "poisson-dc-1.0",
          "is_current": false,
          "p_home": 0.7109,
          "p_draw": 0.196,
          "p_away": 0.0931,
          "pick": "H",
          "confidence": 0.7109,
          "predicted_at": "2026-08-11T21:56:01Z",
          "is_hit": true
        }
      ]
    }
  ]
};
