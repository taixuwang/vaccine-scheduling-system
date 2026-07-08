package scheduler.dto;

public class ReserveRequest {
    private String date;
    private String vaccine;

    public String getDate() { return date; }
    public void setDate(String date) { this.date = date; }
    public String getVaccine() { return vaccine; }
    public void setVaccine(String vaccine) { this.vaccine = vaccine; }
}
