using Microsoft.Web.WebView2.Core;
using Microsoft.Web.WebView2.WinForms;
using System.Diagnostics;

namespace HorariosFamilia.Windows;

internal static class Program
{
    [STAThread]
    private static void Main(string[] args)
    {
        ApplicationConfiguration.Initialize();
        var agendaKey = args
            .FirstOrDefault(a => a.StartsWith("--agenda-key=", StringComparison.OrdinalIgnoreCase))
            ?.Substring("--agenda-key=".Length);
        Application.Run(new MainForm(agendaKey));
    }
}

internal sealed class MainForm : Form
{
    private const string BaseUrl = "https://karlovitch.github.io/horarios-familia-2026-2027/";
    private const string TrustedHost = "karlovitch.github.io";
    private const string TrustedPathPrefix = "/horarios-familia-2026-2027/";

    private readonly WebView2 _webView = new() { Dock = DockStyle.Fill };
    private string? _initialAgendaKey;
    private bool _fullScreen;
    private FormBorderStyle _previousBorderStyle;
    private FormWindowState _previousWindowState;
    private Rectangle _previousBounds;

    public MainForm(string? initialAgendaKey = null)
    {
        _initialAgendaKey = string.IsNullOrWhiteSpace(initialAgendaKey) ? null : initialAgendaKey.Trim();
        Text = "Horários Família";
        StartPosition = FormStartPosition.CenterScreen;
        ClientSize = new Size(1280, 820);
        MinimumSize = new Size(900, 620);
        BackColor = Color.FromArgb(243, 244, 246);
        KeyPreview = true;

        Controls.Add(_webView);

        Shown += async (_, _) => await InitializeWebViewAsync();
        Activated += async (_, _) => await SignalForegroundAsync();
        KeyDown += OnKeyDown;
    }

    private async Task InitializeWebViewAsync()
    {
        try
        {
            var userDataFolder = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                "HorariosFamilia",
                "WebView2");

            var options = new CoreWebView2EnvironmentOptions(
                "--autoplay-policy=no-user-gesture-required");

            var environment = await CoreWebView2Environment.CreateAsync(
                browserExecutableFolder: null,
                userDataFolder: userDataFolder,
                options: options);

            await _webView.EnsureCoreWebView2Async(environment);

            var core = _webView.CoreWebView2;
            core.Settings.IsStatusBarEnabled = false;
            core.Settings.AreBrowserAcceleratorKeysEnabled = true;
            core.Settings.AreDefaultContextMenusEnabled = true;
            core.Settings.IsZoomControlEnabled = true;
            core.Settings.IsBuiltInErrorPageEnabled = true;

            core.PermissionRequested += OnPermissionRequested;
            core.NewWindowRequested += OnNewWindowRequested;
            core.NavigationStarting += OnNavigationStarting;
            core.NavigationCompleted += OnNavigationCompleted;

            NavigateFresh();
        }
        catch (Exception ex)
        {
            var answer = MessageBox.Show(
                "Não foi possível iniciar o motor WebView2 necessário para a aplicação.\n\n" +
                "Em Windows 10/11 este componente normalmente já vem instalado com o Microsoft Edge. " +
                "Se não estiver disponível, pode instalar o Microsoft Edge WebView2 Runtime.\n\n" +
                "Detalhe: " + ex.Message + "\n\nAbrir a página oficial do WebView2?",
                "Horários Família",
                MessageBoxButtons.YesNo,
                MessageBoxIcon.Error);

            if (answer == DialogResult.Yes)
                OpenExternal("https://developer.microsoft.com/microsoft-edge/webview2/");
        }
    }

    private void NavigateFresh()
    {
        if (_webView.CoreWebView2 is null)
            return;

        var stamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds();
        var fragment = "";
        if (!string.IsNullOrWhiteSpace(_initialAgendaKey))
        {
            fragment = "#agendaKey=" + Uri.EscapeDataString(_initialAgendaKey);
            _initialAgendaKey = null;
        }

        _webView.CoreWebView2.Navigate(
            BaseUrl + "?windows=1&shell=1&native=1&__fresh=" + stamp + fragment);
    }

    private async Task SignalForegroundAsync()
    {
        if (_webView.CoreWebView2 is null)
            return;

        try
        {
            await _webView.CoreWebView2.ExecuteScriptAsync(
                "window.dispatchEvent(new Event('appforeground'));" +
                "window.dispatchEvent(new Event('focus'));");
        }
        catch
        {
        }
    }

    private void OnPermissionRequested(
        object? sender,
        CoreWebView2PermissionRequestedEventArgs e)
    {
        if (e.PermissionKind == CoreWebView2PermissionKind.Geolocation &&
            IsTrustedAppUri(e.Uri))
        {
            e.State = CoreWebView2PermissionState.Allow;
        }
    }

    private void OnNewWindowRequested(
        object? sender,
        CoreWebView2NewWindowRequestedEventArgs e)
    {
        e.Handled = true;

        if (IsTrustedAppUri(e.Uri))
        {
            _webView.CoreWebView2?.Navigate(e.Uri);
            return;
        }

        OpenExternal(e.Uri);
    }

    private void OnNavigationStarting(
        object? sender,
        CoreWebView2NavigationStartingEventArgs e)
    {
        if (IsAllowedInternalNavigation(e.Uri))
            return;

        e.Cancel = true;
        OpenExternal(e.Uri);
    }

    private void OnNavigationCompleted(
        object? sender,
        CoreWebView2NavigationCompletedEventArgs e)
    {
        Text = e.IsSuccess ? "Horários Família" : "Horários Família — sem ligação";
    }

    private static bool IsAllowedInternalNavigation(string? uriText)
    {
        if (string.IsNullOrWhiteSpace(uriText))
            return false;

        if (uriText.StartsWith("about:", StringComparison.OrdinalIgnoreCase) ||
            uriText.StartsWith("data:", StringComparison.OrdinalIgnoreCase) ||
            uriText.StartsWith("blob:", StringComparison.OrdinalIgnoreCase))
            return true;

        return IsTrustedAppUri(uriText);
    }

    private static bool IsTrustedAppUri(string? uriText)
    {
        if (!Uri.TryCreate(uriText, UriKind.Absolute, out var uri))
            return false;

        return uri.Scheme.Equals(Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) &&
               uri.Host.Equals(TrustedHost, StringComparison.OrdinalIgnoreCase) &&
               uri.AbsolutePath.StartsWith(
                   TrustedPathPrefix,
                   StringComparison.OrdinalIgnoreCase);
    }

    private static void OpenExternal(string? uri)
    {
        if (string.IsNullOrWhiteSpace(uri))
            return;

        try
        {
            Process.Start(new ProcessStartInfo(uri) { UseShellExecute = true });
        }
        catch
        {
        }
    }

    private void OnKeyDown(object? sender, KeyEventArgs e)
    {
        if (e.KeyCode == Keys.F11)
        {
            ToggleFullScreen();
            e.Handled = true;
            return;
        }

        if (e.KeyCode == Keys.Escape && _fullScreen)
        {
            ToggleFullScreen();
            e.Handled = true;
            return;
        }

        if (e.KeyCode == Keys.F5 || (e.Control && e.KeyCode == Keys.R))
        {
            NavigateFresh();
            e.SuppressKeyPress = true;
            e.Handled = true;
            return;
        }

        if (e.Alt && e.KeyCode == Keys.Left && _webView.CanGoBack)
        {
            _webView.GoBack();
            e.SuppressKeyPress = true;
            e.Handled = true;
            return;
        }

        if (e.Alt && e.KeyCode == Keys.Right && _webView.CanGoForward)
        {
            _webView.GoForward();
            e.SuppressKeyPress = true;
            e.Handled = true;
        }
    }

    private void ToggleFullScreen()
    {
        if (!_fullScreen)
        {
            _previousBounds = Bounds;
            _previousBorderStyle = FormBorderStyle;
            _previousWindowState = WindowState;

            WindowState = FormWindowState.Normal;
            FormBorderStyle = FormBorderStyle.None;
            Bounds = Screen.FromControl(this).Bounds;
            _fullScreen = true;
        }
        else
        {
            FormBorderStyle = _previousBorderStyle;
            WindowState = FormWindowState.Normal;
            Bounds = _previousBounds;
            WindowState = _previousWindowState;
            _fullScreen = false;
        }
    }
}
