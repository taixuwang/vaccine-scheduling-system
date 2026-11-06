package scheduler.util;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.auth0.jwt.interfaces.JWTVerifier;

import java.util.Date;
import java.util.UUID;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import scheduler.db.RedisManager;
import redis.clients.jedis.Jedis;

public class JwtUtil {
    private static final String SECRET_KEY;

    static {
        String envSecret = System.getenv("JwtSecret");
        if (envSecret != null && !envSecret.isEmpty()) {
            SECRET_KEY = envSecret;
        } else {
            SECRET_KEY = "my_super_secret_key_for_vaccine_scheduler"; // fallback for local dev
        }
    }
    private static final long EXPIRATION_TIME_MS = 24 * 60 * 60 * 1000; // 24 hours

    public static String generateToken(String username, String role) {
        Algorithm algorithm = Algorithm.HMAC256(SECRET_KEY);
        return JWT.create()
                .withIssuer("vaccine-scheduler")
                .withJWTId(UUID.randomUUID().toString())
                .withClaim("username", username)
                .withClaim("role", role)
                .withIssuedAt(new Date())
                .withExpiresAt(new Date(System.currentTimeMillis() + EXPIRATION_TIME_MS))
                .sign(algorithm);
    }

    public static DecodedJWT verifyToken(String token) throws JWTVerificationException {
        Algorithm algorithm = Algorithm.HMAC256(SECRET_KEY);
        JWTVerifier verifier = JWT.require(algorithm)
                .withIssuer("vaccine-scheduler")
                .build();
        DecodedJWT jwt = verifier.verify(token);
        try (Jedis jedis = RedisManager.getJedis()) {
            if (jedis.exists(revocationKey(token))) {
                throw new JWTVerificationException("Token has been logged out");
            }
        } catch (JWTVerificationException e) {
            throw e;
        } catch (RuntimeException e) {
            // All nodes consult the same store. Never accept a token when its
            // revocation status cannot be checked.
            throw new JWTVerificationException("Token revocation store unavailable", e);
        }
        return jwt;
    }

    public static void revokeToken(String token) {
        DecodedJWT jwt = verifyToken(token);
        long remainingMillis = jwt.getExpiresAt().getTime() - System.currentTimeMillis();
        if (remainingMillis <= 0) {
            throw new JWTVerificationException("Token has expired");
        }
        long ttlSeconds = (remainingMillis + 999) / 1000;
        try (Jedis jedis = RedisManager.getJedis()) {
            jedis.setex(revocationKey(token), (int) ttlSeconds, "1");
        }
    }

    private static String revocationKey(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                    .digest(token.getBytes(StandardCharsets.UTF_8));
            StringBuilder key = new StringBuilder("auth:revoked:");
            char[] hex = "0123456789abcdef".toCharArray();
            for (byte value : digest) {
                key.append(hex[(value & 0xff) >>> 4]);
                key.append(hex[value & 0xf]);
            }
            return key.toString();
        } catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 is required", e);
        }
    }
}
