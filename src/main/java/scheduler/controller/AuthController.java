package scheduler.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import scheduler.dto.ApiResponse;
import scheduler.dto.AuthRequest;
import scheduler.service.SchedulerService;

@RestController
@RequestMapping("/api/auth")
public class AuthController {

    @Autowired
    private SchedulerService schedulerService;

    @PostMapping("/create_patient")
    public ApiResponse<String> createPatient(@RequestBody AuthRequest request) {
        try {
            String msg = schedulerService.createPatient(request.getUsername(), request.getPassword());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/create_caregiver")
    public ApiResponse<String> createCaregiver(@RequestBody AuthRequest request) {
        try {
            String msg = schedulerService.createCaregiver(request.getUsername(), request.getPassword());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/login_patient")
    public ApiResponse<String> loginPatient(@RequestBody AuthRequest request) {
        try {
            String msg = schedulerService.loginPatient(request.getUsername(), request.getPassword());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/login_caregiver")
    public ApiResponse<String> loginCaregiver(@RequestBody AuthRequest request) {
        try {
            String msg = schedulerService.loginCaregiver(request.getUsername(), request.getPassword());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/logout")
    public ApiResponse<String> logout() {
        try {
            String msg = schedulerService.logout();
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }
}
