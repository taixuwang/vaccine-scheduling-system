-- wrk Lua script: Reserve endpoint throughput (write-heavy)
--
-- Tests: Throughput of the reservation path under sustained write load.
-- Measures: Redis DECR + PostgreSQL transactional write + Nginx load balancing.
--
-- Prerequisites:
--   1. Install wrk (see wrk_login.lua for instructions)
--   2. Set up test data:
--      # Create and login a caregiver
--      TOKEN=$(curl -s -X POST http://localhost/api/auth/create_caregiver \
--              -H "Content-Type: application/json" \
--              -d '{"username":"wrk_cg","password":"Test@123!"}' | jq -r '.data')
--      TOKEN=$(curl -s -X POST http://localhost/api/auth/login_caregiver \
--              -H "Content-Type: application/json" \
--              -d '{"username":"wrk_cg","password":"Test@123!"}' | jq -r '.data')
--
--      # Add availability and doses
--      curl -X POST http://localhost/api/caregiver/upload_availability \
--           -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
--           -d '{"date":"2026-12-01"}'
--      curl -X POST http://localhost/api/caregiver/add_doses \
--           -H "Content-Type: application/json" -H "Authorization: Bearer $TOKEN" \
--           -d '{"vaccine":"WrkVax","number":100000}'
--
--      # Create a test patient and get token
--      curl -s -X POST http://localhost/api/auth/create_patient \
--           -H "Content-Type: application/json" \
--           -d '{"username":"wrk_patient","password":"Test@123!"}'
--      PATIENT_TOKEN=$(curl -s -X POST http://localhost/api/auth/login_patient \
--              -H "Content-Type: application/json" \
--              -d '{"username":"wrk_patient","password":"Test@123!"}' | jq -r '.data')
--      echo "Patient token: $PATIENT_TOKEN"
--
--   3. Replace YOUR_JWT_TOKEN below with the patient JWT token.
--
-- Usage:
--   wrk -t4 -c20 -d30s -s src/test/wrk_reserve.lua http://localhost

-- IMPORTANT: Replace with an actual patient JWT token before running
local token = "YOUR_JWT_TOKEN"

wrk.method = "POST"
wrk.headers["Content-Type"] = "application/json"
wrk.headers["Authorization"] = "Bearer " .. token
wrk.body = '{"date":"2026-12-01","vaccine":"WrkVax"}'
wrk.path = "/api/reservation/reserve"

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
    io.write(string.format("  200 OK (reserved):     %d\n", status_200))
    io.write(string.format("  400 Bad (rejected):    %d\n", status_400))
    io.write(string.format("  Other:                 %d\n", status_other))
    io.write("\nNote: Most 400s are expected (no caregiver slots / already logged in).\n")
    io.write("The 200 count tells you how many reservations succeeded.\n")
end
