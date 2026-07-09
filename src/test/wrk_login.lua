-- wrk Lua script: Login endpoint throughput
--
-- Tests: Raw throughput and latency of the login endpoint.
-- Measures: How fast the server can hash passwords (PBKDF2) and issue JWTs.
--
-- Prerequisites:
--   1. Install wrk: https://github.com/wg/wrk (Linux/macOS)
--      On Windows, use WSL or Docker: docker run --rm williamyeh/wrk ...
--   2. Create a test patient first:
--      curl -X POST http://localhost/api/auth/create_patient \
--           -H "Content-Type: application/json" \
--           -d '{"username":"wrk_patient","password":"Test@123!"}'
--
-- Usage:
--   wrk -t4 -c50 -d30s -s src/test/wrk_login.lua http://localhost
--
-- Flags:
--   -t4     4 threads
--   -c50    50 concurrent connections
--   -d30s   30-second duration

wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.body = '{"username":"wrk_patient","password":"Test@123!"}'
wrk.path = "/api/auth/login_patient"

-- Track response codes
local status_200 = 0
local status_400 = 0
local status_other = 0

response = function(status, headers, body)
    if status == 200 then
        status_200 = status_200 + 1
    elseif status == 400 then
        status_400 = status_400 + 1
    else
        status_other = status_other + 1
    end
end

done = function(summary, latency, requests)
    io.write("\n--- Response Code Breakdown ---\n")
    io.write(string.format("  200 OK:    %d\n", status_200))
    io.write(string.format("  400 Bad:   %d\n", status_400))
    io.write(string.format("  Other:     %d\n", status_other))
end
