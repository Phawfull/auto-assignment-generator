import java.sql.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class TutorialDatabase {
    public static void main(String[] args) throws Exception {
        String user = System.getenv("DB_USER");
        String password = System.getenv("DB_PASSWORD");
        String base = System.getenv("DB_BASE");
        String database = System.getenv("DB_NAME");
        if (args[0].equals("check")) {
            try (Connection connection = DriverManager.getConnection(base, user, password)) {
                System.out.println("MySQL connection successful");
            }
            return;
        }
        if (!database.matches("tutorial_[a-f0-9]{16}")) {
            throw new IllegalArgumentException("Invalid demo database name");
        }
        try (Connection connection = DriverManager.getConnection(base, user, password);
             Statement statement = connection.createStatement()) {
            statement.executeUpdate("CREATE DATABASE `" + database + "`");
        }
        try (Connection connection = DriverManager.getConnection(System.getenv("DB_URL"), user, password);
             Statement statement = connection.createStatement()) {
            for (String line : Files.readAllLines(Path.of("setup.b64"), StandardCharsets.UTF_8)) {
                if (!line.isBlank()) {
                    statement.executeUpdate(new String(Base64.getDecoder().decode(line), StandardCharsets.UTF_8));
                }
            }
        }
        System.out.println("Created demonstration database " + database);
    }
}
