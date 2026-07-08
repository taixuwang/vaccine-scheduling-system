package scheduler.dto;

public class AddDosesRequest {
    private String vaccine;
    private int number;

    public String getVaccine() { return vaccine; }
    public void setVaccine(String vaccine) { this.vaccine = vaccine; }
    public int getNumber() { return number; }
    public void setNumber(int number) { this.number = number; }
}
