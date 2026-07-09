package scheduler.controller;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import scheduler.dto.AddDosesRequest;
import scheduler.dto.ApiResponse;
import scheduler.dto.DateRequest;
import scheduler.service.VaccineService;

@RestController
@RequestMapping("/api/caregiver")
public class VaccineController {

    @Autowired
    private VaccineService vaccineService;

    @PostMapping("/upload_availability")
    public ResponseEntity<ApiResponse<String>> uploadAvailability(@RequestBody DateRequest request) {
        try {
            String msg = vaccineService.uploadAvailability(request.getDate());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }

    @PostMapping("/add_doses")
    public ResponseEntity<ApiResponse<String>> addDoses(@RequestBody AddDosesRequest request) {
        try {
            String msg = vaccineService.addDoses(request.getVaccine(), request.getNumber());
            return ResponseEntity.ok(ApiResponse.success("Success", msg));
        } catch (Exception e) {
            return ResponseEntity.badRequest().body(ApiResponse.error(e.getMessage()));
        }
    }
}
