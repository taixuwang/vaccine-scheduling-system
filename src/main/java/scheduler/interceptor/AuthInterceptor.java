package scheduler.interceptor;

import org.springframework.stereotype.Component;
import org.springframework.web.servlet.HandlerInterceptor;
import scheduler.context.UserContext;
import scheduler.model.Caregiver;
import scheduler.model.Patient;

import javax.servlet.http.HttpServletRequest;
import javax.servlet.http.HttpServletResponse;

@Component
public class AuthInterceptor implements HandlerInterceptor {

    @Override
    public boolean preHandle(HttpServletRequest request, HttpServletResponse response, Object handler) throws Exception {
        String authHeader = request.getHeader("Authorization");
        if (authHeader != null && authHeader.startsWith("Bearer ")) {
            String token = authHeader.substring(7);
            
            if (token.startsWith("Patient:")) {
                String username = token.substring(8);
                Patient p = new Patient.PatientBuilder(username, new byte[0], new byte[0]).build();
                UserContext.setPatient(p);
            } else if (token.startsWith("Caregiver:")) {
                String username = token.substring(10);
                Caregiver c = new Caregiver.CaregiverBuilder(username, new byte[0], new byte[0]).build();
                UserContext.setCaregiver(c);
            }
        }
        return true;
    }

    @Override
    public void afterCompletion(HttpServletRequest request, HttpServletResponse response, Object handler, Exception ex) {
        UserContext.clear();
    }
}
