package scheduler.util;

import java.util.Arrays;
import java.util.Base64;

/** Deterministic PBKDF2 regression vector exercised by test_password_hash.py. */
public class PasswordHashProbe {
    public static void main(String[] args) {
        byte[] salt = new byte[16];
        salt[14] = 0x03;
        salt[15] = 0x76;
        byte[] expected = Base64.getDecoder().decode("5sUK4sNVaotdfkZKLFhPE5VRBwA=");

        byte[] actual = Util.generateHash("Test@123!", salt);
        if (actual.length != 20 || !Arrays.equals(expected, actual) || actual[19] != 0) {
            throw new AssertionError("PBKDF2 parameters or hash bytes do not match the reference vector");
        }
        if (!Util.verifyPassword("Test@123!", salt, expected)) {
            throw new AssertionError("A valid hash ending in zero must verify successfully");
        }
        if (Util.verifyPassword("WrongPass@1", salt, expected)) {
            throw new AssertionError("A wrong password must not verify");
        }
        byte[] altered = expected.clone();
        altered[19] = 1;
        if (Util.verifyPassword("Test@123!", salt, altered)) {
            throw new AssertionError("The final hash byte must be included in comparison");
        }
    }
}
