package scheduler.controller;

import org.springframework.beans.factory.annotation.Autowired;
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
    public ApiResponse<String> uploadAvailability(@RequestBody DateRequest request) {
        try {
            String msg = vaccineService.uploadAvailability(request.getDate());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }

    @PostMapping("/add_doses")
    public ApiResponse<String> addDoses(@RequestBody AddDosesRequest request) {
        try {
            String msg = vaccineService.addDoses(request.getVaccine(), request.getNumber());
            return ApiResponse.success("Success", msg);
        } catch (Exception e) {
            return ApiResponse.error(e.getMessage());
        }
    }
}
