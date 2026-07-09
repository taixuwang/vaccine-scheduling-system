package scheduler.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.bind.annotation.*;
import scheduler.dto.ApiResponse;
import scheduler.dto.DateRequest;
import scheduler.dto.ReserveRequest;
import scheduler.service.ReservationService;
import java.util.List;

@RestController
@RequestMapping("/api/reservation")
public class ReservationController {

    @Autowired
    private ReservationService reservationService;

    @PostMapping("/reserve")
    public ApiResponse<String> reserve(@RequestBody ReserveRequest request) {
        try {
            String msg = reservationService.reserve(request.getDate(), request.getVaccine());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/cancel")
    public ApiResponse<String> cancel(@RequestParam String appointmentId) {
        try {
            String msg = reservationService.cancel(appointmentId);
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/search_caregiver_schedule")
    public ApiResponse<List<String>> searchCaregiverSchedule(@RequestBody DateRequest request) {
        try {
            List<String> result = reservationService.searchCaregiverSchedule(request.getDate());
            return ApiResponse.success("Success", result);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @GetMapping("/show_appointments")
    public ApiResponse<List<String>> showAppointments() {
        try {
            List<String> result = reservationService.showAppointments();
            return ApiResponse.success("Success", result);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }
}
