# Performance Metrics

Collected timings (milliseconds unless the label says otherwise).

Total suite wall-clock: **325.1s**.

| Metric | Value (ms) | Test |
|--------|-----------|------|
| login-reject-ms | 5444 | invalid credentials are rejected with a friendly error |
| login-success-ms | 6757 | successful login, then session-end returns to the guard |
| nav:Document Hub-ms | 1021 | every sidebar route loads its page |
| nav:Knowledge Copilot-ms | 897 | every sidebar route loads its page |
| nav:Knowledge Graph-ms | 713 | every sidebar route loads its page |
| nav:Maintenance-ms | 650 | every sidebar route loads its page |
| nav:Compliance-ms | 874 | every sidebar route loads its page |
| nav:Root Cause-ms | 699 | every sidebar route loads its page |
| nav:Lessons Learned-ms | 679 | every sidebar route loads its page |
| upload-roundtrip-ms | 1277 | uploads a real industrial PDF through the browser and cleans up |
| chat-answer-latency-ms | 53093 | connects over WebSocket and answers a grounded question |
| kg-load-ms | 10522 | renders the seeded P-102A subgraph |
