package scheduler.service;

import org.springframework.stereotype.Service;
import scheduler.context.UserContext;
import scheduler.model.*;
import scheduler.db.*;

import java.sql.Date;
import java.sql.SQLException;

@Service
public class VaccineService {

    public String uploadAvailability(String date) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        try {
            Date d = Date.valueOf(date);
            UserContext.getCaregiver().uploadAvailability(d);
            return "Availability uploaded!";
        } catch (IllegalArgumentException e) {
            throw new RuntimeException("Please enter a valid date!");
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when uploading availability");
        }
    }

    public String addDoses(String vaccineName, int doses) {
        if (UserContext.getCaregiver() == null) {
            throw new RuntimeException("Please login as a caregiver first!");
        }

        Vaccine vaccine = null;
        try {
            vaccine = new Vaccine.VaccineGetter(vaccineName).get();
        } catch (SQLException e) {
            throw new RuntimeException("Error occurred when adding doses");
        }
        
        if (vaccine == null) {
            try {
                vaccine = new Vaccine.VaccineBuilder(vaccineName, doses).build();
                vaccine.saveToDB();
            } catch (SQLException e) {
                throw new RuntimeException("Error occurred when adding doses");
            }
        } else {
            try {
                vaccine.increaseAvailableDoses(doses);
            } catch (SQLException e) {
                throw new RuntimeException("Error occurred when adding doses");
            }
        }

        try (redis.clients.jedis.Jedis jedis = scheduler.db.RedisManager.getJedis()) {
            String redisKey = "vaccine:" + vaccineName + ":doses";
            jedis.incrBy(redisKey, doses);
        } catch (Exception e) {}

        return "Doses updated!";
    }
}
