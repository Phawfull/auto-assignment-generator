import javax.swing.*;
import javax.swing.text.JTextComponent;
import javax.imageio.ImageIO;
import java.awt.*;
import java.io.*;
import java.lang.reflect.InvocationTargetException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.util.Base64;
import java.util.ArrayList;
import java.util.concurrent.atomic.AtomicReference;

public class TutorialRunner {
    static final AtomicReference<Throwable> failure = new AtomicReference<>();
    static final ByteArrayOutputStream output = new ByteArrayOutputStream();
    static int captures = 0;

    static java.util.List<Component> components(Component root) {
        java.util.List<Component> result = new ArrayList<>();
        result.add(root);
        if (root instanceof JMenu) {
            for (Component child : ((JMenu) root).getMenuComponents()) {
                result.addAll(components(child));
            }
        } else if (root instanceof Container) {
            for (Component child : ((Container) root).getComponents()) {
                result.addAll(components(child));
            }
        }
        return result;
    }

    static String text(Component component) {
        if (component instanceof JTextComponent) return ((JTextComponent) component).getText();
        if (component instanceof JLabel) return ((JLabel) component).getText();
        if (component instanceof AbstractButton) return ((AbstractButton) component).getText();
        if (component instanceof JComboBox) return String.valueOf(((JComboBox<?>) component).getSelectedItem());
        if (component instanceof JTable) {
            JTable table = (JTable) component;
            StringBuilder value = new StringBuilder();
            for (int row = 0; row < table.getRowCount(); row++) {
                for (int col = 0; col < table.getColumnCount(); col++) {
                    value.append(table.getValueAt(row, col)).append(" ");
                }
                value.append("\n");
            }
            return value.toString();
        }
        if (component instanceof JOptionPane) return String.valueOf(((JOptionPane) component).getMessage());
        return "";
    }

    static Component find(String name) {
        Window[] windows = Window.getWindows();
        for (int i = windows.length - 1; i >= 0; i--) {
            if (!windows[i].isShowing()) continue;
            for (Component component : components(windows[i])) {
                if (name.equals(component.getName())) return component;
            }
        }
        for (int i = windows.length - 1; i >= 0; i--) {
            if (!windows[i].isShowing()) continue;
            for (Component component : components(windows[i])) {
                if (component.isShowing() && component instanceof AbstractButton
                        && name.equals(text(component))) return component;
            }
        }
        throw new IllegalArgumentException("Cannot find component: " + name);
    }

    static void checked() throws Exception {
        Throwable error = failure.get();
        if (error != null) throw new Exception("Application failed", error);
    }

    static String decoded(String value) {
        return new String(Base64.getDecoder().decode(value), StandardCharsets.UTF_8);
    }

    static void capture(String caption) throws Exception {
        java.util.List<Window> visible = new ArrayList<>();
        SwingUtilities.invokeAndWait(() -> {
            for (Window window : Window.getWindows()) {
                if (window.isShowing()) visible.add(window);
            }
        });
        if (visible.isEmpty()) throw new IllegalStateException("No output window to capture");
        Files.createDirectories(Path.of("screenshots"));
        for (Window window : visible) {
            Rectangle[] bounds = new Rectangle[1];
            SwingUtilities.invokeAndWait(() -> {
                window.setAlwaysOnTop(true);
                window.toFront();
                window.requestFocus();
                bounds[0] = window.getBounds();
            });
            Thread.sleep(650);
            Robot robot = new Robot(window.getGraphicsConfiguration().getDevice());
            String name = String.format("output-%02d.png", ++captures);
            java.awt.image.BufferedImage screenshot = robot.createScreenCapture(bounds[0]);
            final java.awt.image.BufferedImage[] expected = new java.awt.image.BufferedImage[1];
            final Point[] offset = new Point[1];
            SwingUtilities.invokeAndWait(() -> {
                Container content = window instanceof RootPaneContainer
                        ? ((RootPaneContainer) window).getContentPane() : window;
                expected[0] = new java.awt.image.BufferedImage(content.getWidth(), content.getHeight(),
                        java.awt.image.BufferedImage.TYPE_INT_RGB);
                Graphics graphics = expected[0].getGraphics();
                content.printAll(graphics);
                graphics.dispose();
                Point point = content.getLocationOnScreen();
                offset[0] = new Point(point.x - bounds[0].x, point.y - bounds[0].y);
            });
            int matches = 0;
            int samples = 0;
            for (int y = 8; y < expected[0].getHeight() - 8; y += 13) {
                for (int x = 8; x < expected[0].getWidth() - 8; x += 13) {
                    int sx = x + offset[0].x;
                    int sy = y + offset[0].y;
                    if (sx < 0 || sy < 0 || sx >= screenshot.getWidth() || sy >= screenshot.getHeight()) continue;
                    Color actual = new Color(screenshot.getRGB(sx, sy));
                    Color reference = new Color(expected[0].getRGB(x, y));
                    int difference = Math.abs(actual.getRed() - reference.getRed())
                            + Math.abs(actual.getGreen() - reference.getGreen())
                            + Math.abs(actual.getBlue() - reference.getBlue());
                    if (difference < 45) matches++;
                    samples++;
                }
            }
            if (samples == 0 || matches < samples * 0.72) {
                throw new IllegalStateException("Output screenshot is obscured or desktop scaling is incompatible. Keep the desktop unlocked and output windows visible.");
            }
            ImageIO.write(screenshot, "png", Path.of("screenshots", name).toFile());
            String line = name + "\t" + Base64.getEncoder().encodeToString(caption.getBytes(StandardCharsets.UTF_8)) + "\n";
            Files.writeString(Path.of("screenshots", "captions.tsv"), line,
                    StandardCharsets.UTF_8, StandardOpenOption.CREATE, StandardOpenOption.APPEND);
        }
    }

    static void execute(String action, String target, String value) throws Exception {
        if (action.equals("wait")) {
            Thread.sleep(Math.min(5000, Math.max(0, Integer.parseInt(value))));
        } else if (action.equals("capture")) {
            capture(value);
        } else if (action.equals("click")) {
            SwingUtilities.invokeAndWait(() -> {
                AbstractButton button = (AbstractButton) find(target);
                if (!button.isEnabled()) throw new IllegalStateException("Disabled button: " + target);
                SwingUtilities.invokeLater(() -> button.doClick());
            });
            Thread.sleep(500);
        } else {
            SwingUtilities.invokeAndWait(() -> {
                if (action.equals("text")) {
                    ((JTextComponent) find(target)).setText(value);
                } else if (action.equals("select")) {
                    Component component = find(target);
                    if (component instanceof JComboBox) ((JComboBox<?>) component).setSelectedItem(value);
                    else ((AbstractButton) component).setSelected(Boolean.parseBoolean(value));
                } else if (action.equals("assert")) {
                    StringBuilder actual = new StringBuilder();
                    if (!target.isEmpty()) actual.append(text(find(target)));
                    else {
                        actual.append(output.toString(StandardCharsets.UTF_8));
                        for (Window window : Window.getWindows()) {
                            if (!window.isShowing()) continue;
                            for (Component component : components(window)) {
                                if (component.isShowing()) actual.append(text(component)).append("\n");
                            }
                        }
                    }
                    if (!actual.toString().contains(value)) {
                        throw new IllegalStateException("Expected [" + value + "] in " + target + "; actual: " + actual);
                    }
                } else throw new IllegalArgumentException("Unknown action: " + action);
            });
        }
        checked();
    }

    public static void main(String[] args) {
        PrintStream original = System.out;
        try {
            Thread.setDefaultUncaughtExceptionHandler((thread, error) -> failure.compareAndSet(null, error));
            System.setOut(new PrintStream(output, true, StandardCharsets.UTF_8));
            System.setErr(System.out);
            System.setIn(new ByteArrayInputStream(Files.readAllBytes(Path.of("stdin.txt"))));
            Class.forName(args[0]).getMethod("main", String[].class).invoke(null, (Object) new String[0]);
            Thread.sleep(700);
            checked();
            if (args[1].equals("console")) {
                String actual = output.toString(StandardCharsets.UTF_8);
                if (actual.isBlank()) throw new IllegalStateException("Program produced no output");
                Files.writeString(Path.of("stdout.txt"), actual, StandardCharsets.UTF_8);
                SwingUtilities.invokeAndWait(() -> {
                    JFrame frame = new JFrame(args[0] + " — Program output");
                    JTextArea area = new JTextArea(actual);
                    area.setName("consoleOutput");
                    area.setEditable(false);
                    area.setFont(new Font(Font.MONOSPACED, Font.PLAIN, 16));
                    area.setBackground(new Color(24, 27, 32));
                    area.setForeground(Color.WHITE);
                    area.setMargin(new Insets(15, 15, 15, 15));
                    frame.add(new JScrollPane(area));
                    frame.setSize(880, 620);
                    frame.setLocationRelativeTo(null);
                    frame.setVisible(true);
                });
            }
            for (String line : Files.readAllLines(Path.of("steps.tsv"), StandardCharsets.UTF_8)) {
                String[] cells = line.split("\t", -1);
                execute(cells[0], decoded(cells[1]), decoded(cells[2]));
            }
            checked();
            Files.writeString(Path.of("stdout.txt"), output.toString(StandardCharsets.UTF_8), StandardCharsets.UTF_8);
            if (captures == 0) throw new IllegalStateException("No screenshots captured");
            original.println("RUN_OK screenshots=" + captures);
            System.exit(0);
        } catch (Throwable error) {
            original.println(output.toString(StandardCharsets.UTF_8));
            error.printStackTrace(original);
            System.exit(1);
        }
    }
}
