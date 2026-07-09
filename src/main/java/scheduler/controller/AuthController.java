package scheduler.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import scheduler.dto.ApiResponse;
import scheduler.dto.AuthRequest;
import scheduler.service.AuthService;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    @Autowired
    private AuthService authService;

    @PostMapping("/create_patient")
    public ResponseEntity<ApiResponse<String>> createPatient(@RequestBody AuthRequest request) {
        try {
            String msg = authService.createPatient(request.getUsername(), request.getPassword());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }

    @PostMapping("/create_caregiver")
    public ResponseEntity<ApiResponse<String>> createCaregiver(@RequestBody AuthRequest request) {
        try {
            String msg = authService.createCaregiver(request.getUsername(), request.getPassword());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }

    @PostMapping("/login_patient")
    public ResponseEntity<ApiResponse<String>> loginPatient(@RequestBody AuthRequest request) {
        try {
            String msg = authService.loginPatient(request.getUsername(), request.getPassword());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }

    @PostMapping("/login_caregiver")
    public ResponseEntity<ApiResponse<String>> loginCaregiver(@RequestBody AuthRequest request) {
        try {
            String msg = authService.loginCaregiver(request.getUsername(), request.getPassword());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }

    @PostMapping("/logout")
    public ResponseEntity<ApiResponse<String>> logout() {
        try {
            String msg = authService.logout();
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }
}
