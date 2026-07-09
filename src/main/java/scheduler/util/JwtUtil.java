package scheduler.util;

import com.auth0.jwt.JWT;
import com.auth0.jwt.algorithms.Algorithm;
import com.auth0.jwt.exceptions.JWTVerificationException;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.auth0.jwt.interfaces.JWTVerifier;

import java.util.Date;

public class JwtUtil {
    // In a real application, this secret should be stored securely (e.g., environment variable)
    private static final String SECRET_KEY = "my_super_secret_key_for_vaccine_scheduler";
    private static final long EXPIRATION_TIME_MS = 24 * 60 * 60 * 1000; // 24 hours

    public static String generateToken(String username, String role) {
        Algorithm algorithm = Algorithm.HMAC256(SECRET_KEY);
        return JWT.create()
                .withIssuer("vaccine-scheduler")
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
        return verifier.verify(token);
    }
}
