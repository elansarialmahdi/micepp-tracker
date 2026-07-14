using System.Diagnostics;
using System.Drawing;
using System.Text;

namespace MiceppManager;

internal static class Program
{
    [STAThread]
    private static void Main()
    {
        ApplicationConfiguration.Initialize();
        Application.Run(new ManagerForm());
    }
}

internal sealed class ManagerForm : Form
{
    private readonly string projectDirectory;
    private readonly Label overallStatus = new();
    private readonly TextBox output = new();
    private readonly Button startButton = CreateButton("Démarrer", Color.FromArgb(22, 163, 74));
    private readonly Button stopButton = CreateButton("Arrêter", Color.FromArgb(220, 38, 38));
    private readonly Button restartButton = CreateButton("Redémarrer", Color.FromArgb(37, 99, 235));
    private readonly Button rebuildButton = CreateButton("Reconstruire", Color.FromArgb(124, 58, 237));
    private readonly Button openButton = CreateButton("Ouvrir le site", Color.FromArgb(15, 118, 110));
    private readonly Button refreshButton = CreateButton("Actualiser l’état", Color.FromArgb(71, 85, 105));
    private readonly Button logsButton = CreateButton("Afficher les logs", Color.FromArgb(71, 85, 105));
    private readonly System.Windows.Forms.Timer refreshTimer = new() { Interval = 5000 };
    private bool operationRunning;

    public ManagerForm()
    {
        projectDirectory = LocateProjectDirectory();
        Text = "Gestionnaire MICEPP";
        StartPosition = FormStartPosition.CenterScreen;
        MinimumSize = new Size(760, 560);
        Size = new Size(860, 650);
        BackColor = Color.FromArgb(248, 250, 252);
        Font = new Font("Segoe UI", 10F);

        var title = new Label
        {
            Text = "MICEPP — Gestion des services",
            AutoSize = true,
            Font = new Font("Segoe UI Semibold", 18F),
            ForeColor = Color.FromArgb(15, 23, 42),
            Margin = new Padding(0, 0, 0, 4),
        };
        var subtitle = new Label
        {
            Text = "Démarrez ou relancez toute l’application sans utiliser de commandes.",
            AutoSize = true,
            ForeColor = Color.FromArgb(71, 85, 105),
            Margin = new Padding(0, 0, 0, 14),
        };

        overallStatus.AutoSize = true;
        overallStatus.Font = new Font("Segoe UI Semibold", 11F);
        overallStatus.Padding = new Padding(10, 7, 10, 7);
        overallStatus.Margin = new Padding(0, 0, 0, 14);
        SetStatus("Vérification de Docker…", Color.FromArgb(161, 98, 7), Color.FromArgb(254, 249, 195));

        var actions = new FlowLayoutPanel
        {
            AutoSize = true,
            AutoSizeMode = AutoSizeMode.GrowAndShrink,
            Dock = DockStyle.Fill,
            WrapContents = true,
            Margin = new Padding(0, 0, 0, 12),
        };
        actions.Controls.AddRange([startButton, stopButton, restartButton, rebuildButton, openButton]);

        var secondaryActions = new FlowLayoutPanel
        {
            AutoSize = true,
            Dock = DockStyle.Fill,
            Margin = new Padding(0, 0, 0, 10),
        };
        secondaryActions.Controls.AddRange([refreshButton, logsButton]);

        output.Multiline = true;
        output.ReadOnly = true;
        output.ScrollBars = ScrollBars.Both;
        output.WordWrap = false;
        output.Dock = DockStyle.Fill;
        output.BackColor = Color.FromArgb(15, 23, 42);
        output.ForeColor = Color.FromArgb(226, 232, 240);
        output.Font = new Font("Consolas", 9.5F);
        output.BorderStyle = BorderStyle.FixedSingle;

        var layout = new TableLayoutPanel
        {
            Dock = DockStyle.Fill,
            ColumnCount = 1,
            RowCount = 7,
            Padding = new Padding(24),
        };
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.AutoSize));
        layout.RowStyles.Add(new RowStyle(SizeType.Percent, 100));
        layout.Controls.Add(title, 0, 0);
        layout.Controls.Add(subtitle, 0, 1);
        layout.Controls.Add(overallStatus, 0, 2);
        layout.Controls.Add(actions, 0, 3);
        layout.Controls.Add(secondaryActions, 0, 4);
        layout.Controls.Add(new Label { Text = $"Projet : {projectDirectory}", AutoSize = true, ForeColor = Color.FromArgb(100, 116, 139), Margin = new Padding(0, 0, 0, 8) }, 0, 5);
        layout.Controls.Add(output, 0, 6);
        Controls.Add(layout);

        startButton.Click += async (_, _) => await RunOperationAsync("Démarrage de MICEPP", ["compose", "up", "-d"]);
        stopButton.Click += async (_, _) => await RunOperationAsync("Arrêt de MICEPP", ["compose", "stop"]);
        restartButton.Click += async (_, _) => await RunOperationAsync("Redémarrage de MICEPP", ["compose", "restart"]);
        rebuildButton.Click += async (_, _) => await RunOperationAsync("Reconstruction et redémarrage", ["compose", "up", "-d", "--build"]);
        openButton.Click += (_, _) => OpenSite();
        refreshButton.Click += async (_, _) => await RefreshStatusAsync(true);
        logsButton.Click += async (_, _) => await ShowLogsAsync();
        refreshTimer.Tick += async (_, _) => await RefreshStatusAsync(false);
        Shown += async (_, _) =>
        {
            await RefreshStatusAsync(true);
            refreshTimer.Start();
        };
    }

    private static Button CreateButton(string text, Color color) => new()
    {
        Text = text,
        AutoSize = true,
        MinimumSize = new Size(115, 40),
        BackColor = color,
        ForeColor = Color.White,
        FlatStyle = FlatStyle.Flat,
        Cursor = Cursors.Hand,
        Margin = new Padding(0, 0, 8, 8),
    };

    private static string LocateProjectDirectory()
    {
        var candidates = new[]
        {
            AppContext.BaseDirectory,
            Environment.CurrentDirectory,
            Path.GetFullPath(Path.Combine(AppContext.BaseDirectory, "..", "..")),
        };
        return candidates.FirstOrDefault(path => File.Exists(Path.Combine(path, "docker-compose.yml")))
            ?? AppContext.BaseDirectory;
    }

    private async Task RunOperationAsync(string title, string[] arguments)
    {
        if (operationRunning) return;
        SetBusy(true);
        Append($"\r\n=== {title} ===\r\n");
        var result = await RunDockerAsync(arguments);
        Append(result.CombinedOutput);
        if (result.ExitCode == 0)
            Append("\r\nOpération terminée avec succès.\r\n");
        else
            Append($"\r\nÉchec de l’opération (code {result.ExitCode}).\r\n");
        SetBusy(false);
        await RefreshStatusAsync(false);
    }

    private async Task RefreshStatusAsync(bool writeDetails)
    {
        if (operationRunning) return;
        var result = await RunDockerAsync(["compose", "ps", "--format", "{{.Service}}|{{.State}}"]);
        if (result.ExitCode != 0)
        {
            SetStatus("Docker indisponible", Color.FromArgb(185, 28, 28), Color.FromArgb(254, 226, 226));
            if (writeDetails) Append(result.CombinedOutput);
            return;
        }

        var lines = result.StandardOutput.Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries);
        var running = lines.Count(line => line.EndsWith("|running", StringComparison.OrdinalIgnoreCase));
        var total = lines.Length;
        if (total >= 9 && running == total)
            SetStatus($"Application opérationnelle — {running}/{total} services actifs", Color.FromArgb(21, 128, 61), Color.FromArgb(220, 252, 231));
        else if (running > 0)
            SetStatus($"Démarrage partiel — {running}/{Math.Max(total, 9)} services actifs", Color.FromArgb(161, 98, 7), Color.FromArgb(254, 249, 195));
        else
            SetStatus("Application arrêtée", Color.FromArgb(71, 85, 105), Color.FromArgb(226, 232, 240));
        if (writeDetails)
        {
            output.Text = total == 0 ? "Aucun service actif.\r\n" : string.Join("\r\n", lines.Select(line => line.Replace('|', ' '))) + "\r\n";
        }
    }

    private async Task ShowLogsAsync()
    {
        if (operationRunning) return;
        SetBusy(true);
        output.Text = "Chargement des derniers logs…\r\n";
        var result = await RunDockerAsync(["compose", "logs", "--tail", "120", "api", "frontend", "protection-worker", "scanner-worker"]);
        output.Text = result.CombinedOutput;
        output.SelectionStart = output.TextLength;
        output.ScrollToCaret();
        SetBusy(false);
    }

    private async Task<CommandResult> RunDockerAsync(string[] arguments)
    {
        try
        {
            var startInfo = new ProcessStartInfo
            {
                FileName = "docker.exe",
                WorkingDirectory = projectDirectory,
                UseShellExecute = false,
                CreateNoWindow = true,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                StandardOutputEncoding = Encoding.UTF8,
                StandardErrorEncoding = Encoding.UTF8,
            };
            foreach (var argument in arguments) startInfo.ArgumentList.Add(argument);
            using var process = new Process { StartInfo = startInfo };
            process.Start();
            var stdoutTask = process.StandardOutput.ReadToEndAsync();
            var stderrTask = process.StandardError.ReadToEndAsync();
            await process.WaitForExitAsync();
            var stdout = await stdoutTask;
            var stderr = await stderrTask;
            return new CommandResult(process.ExitCode, stdout, stderr);
        }
        catch (Exception exception)
        {
            return new CommandResult(-1, "", $"Impossible d’exécuter Docker : {exception.Message}\r\nVérifiez que Docker Desktop est installé et démarré.\r\n");
        }
    }

    private void OpenSite()
    {
        try
        {
            Process.Start(new ProcessStartInfo("http://localhost:8081") { UseShellExecute = true });
        }
        catch (Exception exception)
        {
            MessageBox.Show(this, exception.Message, "Impossible d’ouvrir le site", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void SetBusy(bool busy)
    {
        operationRunning = busy;
        foreach (var button in new[] { startButton, stopButton, restartButton, rebuildButton, refreshButton, logsButton })
            button.Enabled = !busy;
        if (busy) SetStatus("Opération en cours…", Color.FromArgb(29, 78, 216), Color.FromArgb(219, 234, 254));
        UseWaitCursor = busy;
    }

    private void SetStatus(string text, Color foreground, Color background)
    {
        overallStatus.Text = text;
        overallStatus.ForeColor = foreground;
        overallStatus.BackColor = background;
    }

    private void Append(string text)
    {
        output.AppendText(text);
        output.SelectionStart = output.TextLength;
        output.ScrollToCaret();
    }

    private sealed record CommandResult(int ExitCode, string StandardOutput, string StandardError)
    {
        public string CombinedOutput => StandardOutput + StandardError;
    }
}
