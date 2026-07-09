package scheduler.interceptor;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import scheduler.context.UserContext;
import scheduler.model.Caregiver;
import scheduler.model.Patient;
import scheduler.util.JwtUtil;
import com.auth0.jwt.interfaces.DecodedJWT;
import com.auth0.jwt.exceptions.JWTVerificationException;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@Component
public class AuthInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            
            try {
                DecodedJWT jwt = JwtUtil.verifyToken(token);
                String username = jwt.getClaim("username").asString();
                String role = jwt.getClaim("role").asString();
                
                if ("Patient".equals(role)) {
                    Patient p = new Patient.PatientBuilder(username, new byte[0], new byte[0]).build();
                    UserContext.setPatient(p);
                } else if ("Caregiver".equals(role)) {
                    Caregiver c = new Caregiver.CaregiverBuilder(username, new byte[0], new byte[0]).build();
                    UserContext.setCaregiver(c);
                }
            } catch (JWTVerificationException e) {
                // Invalid token, do not set user context
            }
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        UserContext.clear();
    }
}
