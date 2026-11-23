using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Net;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;
using System.Web.Script.Serialization;
using System.Windows.Forms;

internal static class ReviewSetup
{
    private const string Repository = "xtltt56-cmd/src-auto-authorized-security-testing";
    private const string Launcher = "SRC-Auto-Review.exe";
    private const string Updater = "SRC-Auto-Review-Update.exe";
    private const string Title = "SRC-Auto 本地审阅版";
    private const long MaxZip = 128L * 1024 * 1024;
    private static readonly Regex TagPattern = new Regex(@"\Areview-v(\d+\.\d+\.\d+)\z", RegexOptions.CultureInvariant);
    private static readonly Regex VersionPattern = new Regex(@"\A\d+\.\d+\.\d+\z", RegexOptions.CultureInvariant);

    internal sealed class Asset
    {
        public string Version, Digest;
        public long Size;
        public Uri Url;
    }

    [STAThread]
    public static int Main(string[] args)
    {
        try
        {
            Application.EnableVisualStyles();
            ServicePointManager.SecurityProtocol = SecurityProtocolType.Tls12;
            string exe = Assembly.GetExecutingAssembly().Location;
            if (Path.GetFileName(exe).Equals(Launcher, StringComparison.OrdinalIgnoreCase))
            {
                Launch(Path.GetDirectoryName(exe));
                return 0;
            }

            string root;
            if (Path.GetFileName(exe).Equals(Updater, StringComparison.OrdinalIgnoreCase))
                root = Path.GetDirectoryName(exe);
            else
                using (var folder = new FolderBrowserDialog())
                {
                    folder.Description = "选择安装的上级目录，将创建 SRC-Auto-Review 子目录。";
                    if (folder.ShowDialog() != DialogResult.OK) return 0;
                    root = Path.Combine(folder.SelectedPath, "SRC-Auto-Review");
                }

            root = Path.GetFullPath(root);
            CheckDirectory(root, true);
            Directory.CreateDirectory(root);
            string marker = Path.Combine(root, ".src-auto-review");
            if (!File.Exists(marker))
            {
                if (Directory.GetFileSystemEntries(root).Length != 0)
                    throw new InvalidOperationException("安装目标已经有其他文件。请选择空目录。");
                using (File.Create(marker)) { }
            }
            CheckDirectory(root, false);
            using (var guard = new FileStream(Path.Combine(root, ".install.lock"), FileMode.OpenOrCreate,
                                               FileAccess.ReadWrite, FileShare.None))
            {
                var state = ReadState(root);
                return RunMenu(root, exe, state);
            }
        }
        catch (Exception e)
        {
            MessageBox.Show("操作未完成。\n" + e.Message, Title, MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return 1;
        }
    }

    private static int RunMenu(string root, string exe, string[] state)
    {
        if (state[0] != "")
        {
            if (state[1] != "")
            {
                var choice = MessageBox.Show("当前版本 v" + state[0] +
                    "\n\n是：联网检查更新\n否：回退至 v" + state[1] + "\n取消：退出",
                    Title, MessageBoxButtons.YesNoCancel);
                if (choice == DialogResult.Cancel) return 0;
                if (choice == DialogResult.No) { Rollback(root); Launch(root); return 0; }
            }
            else if (MessageBox.Show("当前版本 v" + state[0] + "\n\n联网检查更新？", Title,
                                     MessageBoxButtons.OKCancel) != DialogResult.OK) return 0;
        }

        Asset asset = Latest();
        if (state[0] != "" && Version.Parse(asset.Version) <= Version.Parse(state[0]))
        {
            MessageBox.Show("当前已安装 v" + state[0] + "。", Title);
            return 0;
        }
        if (MessageBox.Show("版本 v" + asset.Version + "\n下载大小约 " +
            Math.Ceiling(asset.Size / 1048576.0) + " MiB\n安装目录 " + root + "\n\n开始下载并安装？", Title,
            MessageBoxButtons.OKCancel) != DialogResult.OK) return 0;

        string zip = Path.Combine(root, ".download-" + Guid.NewGuid().ToString("N"));
        try
        {
            using (var progress = new Form {Text = Title, Width = 420, Height = 120,
                StartPosition = FormStartPosition.CenterScreen, ControlBox = false,
                FormBorderStyle = FormBorderStyle.FixedDialog})
            {
                var status = new Label {Text = "正在下载正式包…", Dock = DockStyle.Fill,
                    TextAlign = System.Drawing.ContentAlignment.MiddleCenter};
                progress.Controls.Add(status);
                progress.Show();
                progress.Refresh();
                using (var stream = new FileStream(zip, FileMode.CreateNew)) Download(asset.Url, stream, asset.Size);
                status.Text = "正在校验、解压并运行本地自检…";
                progress.Refresh();
                foreach (string name in new[] {Launcher, Updater})
                {
                    string entry = Path.Combine(root, name);
                    if (!File.Exists(entry)) File.Copy(exe, entry);
                }
                Install(root, zip, asset);
            }
        }
        finally { if (File.Exists(zip)) File.Delete(zip); }
        Launch(root);
        return 0;
    }

    internal static Asset ParseReleases(string json)
    {
        var list = new JavaScriptSerializer { MaxJsonLength = 4 * 1024 * 1024 }
            .Deserialize<Dictionary<string, object>[]>(json);
        Asset best = null;
        foreach (var release in list)
        {
            var match = TagPattern.Match((string)release["tag_name"]);
            if (!match.Success || (bool)release["draft"] || (bool)release["prerelease"]) continue;
            string version = match.Groups[1].Value;
            if (best != null && Version.Parse(version) <= Version.Parse(best.Version)) continue;
            string name = "SRC-Auto-Review-v" + version + "-win-x64.zip";
            var expected = new Uri("https://github.com/" + Repository + "/releases/download/" + match.Value + "/" + name);
            var rows = (System.Collections.ArrayList)release["assets"];
            foreach (Dictionary<string, object> row in rows)
            {
                if (!string.Equals((string)row["name"], name, StringComparison.Ordinal)) continue;
                var size = Convert.ToInt64(row["size"]);
                var digest = row.ContainsKey("digest") ? row["digest"] as string : null;
                if (!string.Equals((string)row["browser_download_url"], expected.AbsoluteUri, StringComparison.Ordinal) ||
                    digest == null || !Regex.IsMatch(digest, @"\Asha256:[0-9a-fA-F]{64}\z") || size < 1 || size > MaxZip)
                    throw new InvalidDataException("发行资产的地址、大小或 SHA-256 摘要不符合要求。");
                best = new Asset {Version = version, Digest = digest.Substring(7), Size = size, Url = expected};
            }
        }
        return best;
    }

    private static Asset Latest()
    {
        Asset best = null;
        for (int page = 1; page <= 5; page++)
        {
            using (var output = new MemoryStream())
            {
                string next = Download(new Uri("https://api.github.com/repos/" + Repository +
                    "/releases?per_page=30&page=" + page), output, 4 * 1024 * 1024);
                var candidate = ParseReleases(Encoding.UTF8.GetString(output.ToArray()));
                if (candidate != null && (best == null ||
                    Version.Parse(candidate.Version) > Version.Parse(best.Version))) best = candidate;
                if (string.IsNullOrEmpty(next) || !next.Contains("rel=\"next\""))
                {
                    if (best != null) return best;
                    throw new InvalidOperationException("GitHub 暂无可用的本地审阅版正式资产。");
                }
            }
        }
        throw new InvalidOperationException("发布列表超出检查范围，无法确认最新版本。");
    }

    private static string Download(Uri uri, Stream destination, long maximum)
    {
        var allowed = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "api.github.com", "github.com",
            "release-assets.githubusercontent.com", "objects.githubusercontent.com" };
        for (int hop = 0; hop < 5; hop++)
        {
            if (uri.Scheme != Uri.UriSchemeHttps || !uri.IsDefaultPort || uri.UserInfo != "" || !allowed.Contains(uri.Host))
                throw new InvalidDataException("下载跳转地址超出 GitHub 允许范围。");
            var request = (HttpWebRequest)WebRequest.Create(uri);
            request.AllowAutoRedirect = false;
            request.UserAgent = "SRC-Auto-Review-Setup/1";
            request.Accept = "application/vnd.github+json, application/octet-stream";
            request.Timeout = 30000;
            request.ReadWriteTimeout = 30000;
            using (var response = (HttpWebResponse)request.GetResponse())
            {
                int status = (int)response.StatusCode;
                if (status >= 300 && status < 400)
                {
                    uri = new Uri(uri, response.Headers["Location"]);
                    continue;
                }
                if (status != 200 || response.ContentLength > maximum)
                    throw new InvalidDataException("下载响应无效或超过大小上限。");
                var buffer = new byte[65536];
                long count = 0;
                using (var input = response.GetResponseStream())
                {
                    int n;
                    var timer = Stopwatch.StartNew();
                    while ((n = input.Read(buffer, 0, buffer.Length)) != 0)
                    {
                        count += n;
                        if (count > maximum || timer.Elapsed.TotalMinutes > 10)
                            throw new InvalidDataException("下载超过大小或时间上限。");
                        destination.Write(buffer, 0, n);
                    }
                }
                return response.Headers["Link"];
            }
        }
        throw new InvalidDataException("下载跳转次数超出上限。");
    }

    internal static void Install(string root, string zip, Asset asset)
    {
        if (!VersionPattern.IsMatch(asset.Version)) throw new InvalidDataException("版本标识无效。");
        string versions = Path.Combine(root, "versions");
        CheckDirectory(versions, true);
        Directory.CreateDirectory(versions);
        string versionPath = Path.Combine(versions, "v" + asset.Version);
        CheckDirectory(versionPath, true);
        string stage = Path.Combine(versions, ".staging-" + Guid.NewGuid().ToString("N"));
        using (var input = File.OpenRead(zip))
        {
            string digest;
            using (var algorithm = SHA256.Create())
                digest = BitConverter.ToString(algorithm.ComputeHash(input)).Replace("-", "");
            if (input.Length != asset.Size || !digest.Equals(asset.Digest, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException("ZIP 大小或 SHA-256 校验失败。");
            input.Position = 0;
            if (!Directory.Exists(versionPath))
            {
                Directory.CreateDirectory(stage);
                try
                {
                    Extract(input, stage);
                    if (File.ReadAllText(Path.Combine(stage, "VERSION")).Trim() != asset.Version)
                        throw new InvalidDataException("ZIP 内版本与发行版本不一致。");
                    Smoke(stage);
                    File.WriteAllText(Path.Combine(stage, ".installed-sha256"), asset.Digest, Encoding.ASCII);
                    Directory.Move(stage, versionPath);
                }
                finally { if (Directory.Exists(stage)) Directory.Delete(stage, true); }
            }
            else
            {
                if (!File.ReadAllText(Path.Combine(versionPath, ".installed-sha256")).Equals(asset.Digest, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("已安装目录与下载版本的摘要记录不一致。");
                Smoke(versionPath);
            }
        }
        var state = ReadState(root);
        if (state[0] != asset.Version) WriteState(root, asset.Version, state[0]);
    }

    internal static void Extract(Stream input, string stage)
    {
        using (var zip = new ZipArchive(input, ZipArchiveMode.Read, true))
        {
            var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            long expanded = 0;
            if (zip.Entries.Count > 15000) throw new InvalidDataException("ZIP 文件数超出上限。");
            foreach (var entry in zip.Entries)
            {
                string name = entry.FullName.Replace('\\', '/');
                bool directory = name.EndsWith("/", StringComparison.Ordinal);
                name = directory ? name.Substring(0, name.Length - 1) : name;
                foreach (string part in name.Split('/'))
                {
                    if (part == "" || part.EndsWith(".") || part.EndsWith(" ") ||
                        part.IndexOfAny(Path.GetInvalidFileNameChars()) >= 0 ||
                        Regex.IsMatch(part, @"\A(CON|PRN|AUX|NUL|COM[0-9¹²³]|LPT[0-9¹²³])(\.|$)", RegexOptions.IgnoreCase))
                        throw new InvalidDataException("ZIP 包含无效路径。");
                }
                expanded += entry.Length;
                if (!paths.Add(name) || expanded > 350L * 1024 * 1024 ||
                    ((entry.ExternalAttributes >> 16) & 0xF000) == 0xA000)
                    throw new InvalidDataException("ZIP 包含重复路径、链接或超过解压上限。");
                string full = Path.GetFullPath(Path.Combine(stage, name.Replace('/', '\\')));
                if (!full.StartsWith(stage + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))
                    throw new InvalidDataException("ZIP 解压路径越界。");
                if (directory) Directory.CreateDirectory(full);
                else
                {
                    Directory.CreateDirectory(Path.GetDirectoryName(full));
                    using (var source = entry.Open())
                    using (var destination = new FileStream(full, FileMode.CreateNew))
                    {
                        var buffer = new byte[65536];
                        long copied = 0;
                        int n;
                        while ((n = source.Read(buffer, 0, buffer.Length)) > 0)
                        {
                            copied += n;
                            if (copied > entry.Length) throw new InvalidDataException("ZIP 内容长度不一致。");
                            destination.Write(buffer, 0, n);
                        }
                        if (copied != entry.Length) throw new InvalidDataException("ZIP 内容长度不一致。");
                    }
                }
            }
        }
    }

    private static void CheckDirectory(string path, bool allowMissing)
    {
        if (path.StartsWith(@"\\", StringComparison.Ordinal))
            throw new InvalidOperationException("请选择本机磁盘上的目录。");
        for (var d = new DirectoryInfo(path); d != null; d = d.Parent)
        {
            FileAttributes attributes;
            try { attributes = File.GetAttributes(d.FullName); }
            catch (FileNotFoundException) { if (allowMissing) continue; throw; }
            catch (DirectoryNotFoundException) { if (allowMissing) continue; throw; }
            if ((attributes & FileAttributes.ReparsePoint) != 0 || (attributes & FileAttributes.Directory) == 0)
                throw new InvalidOperationException("安装目录不能经过联接、重解析点或普通文件。");
        }
    }

    private static string[] ReadState(string root)
    {
        string path = Path.Combine(root, "active.txt");
        if (!File.Exists(path)) return new[] {"", ""};
        var state = File.ReadAllLines(path);
        if (state.Length != 2 || !VersionPattern.IsMatch(state[0]) ||
            (state[1] != "" && !VersionPattern.IsMatch(state[1])))
            throw new InvalidDataException("安装版本状态文件无效。");
        return state;
    }

    private static void WriteState(string root, string current, string previous)
    {
        string path = Path.Combine(root, "active.txt");
        string temporary = path + "." + Guid.NewGuid().ToString("N");
        try
        {
            File.WriteAllLines(temporary, new[] {current, previous}, Encoding.ASCII);
            if (File.Exists(path)) File.Replace(temporary, path, null);
            else File.Move(temporary, path);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }

    private static string VersionPath(string root, string version)
    {
        if (!VersionPattern.IsMatch(version)) throw new InvalidDataException("没有可启动的已安装版本。");
        string path = Path.Combine(root, "versions", "v" + version);
        CheckDirectory(path, false);
        if (!File.Exists(Path.Combine(path, ".installed-sha256")))
            throw new InvalidDataException("找不到完整安装的版本。");
        return path;
    }

    internal static void Rollback(string root)
    {
        var state = ReadState(root);
        Smoke(VersionPath(root, state[1]));
        WriteState(root, state[1], state[0]);
    }

    private static ProcessStartInfo Entry(string path, bool smoke)
    {
        return new ProcessStartInfo {
            FileName = Path.Combine(path, "python", smoke ? "python.exe" : "pythonw.exe"),
            Arguments = "-I -B \"" + Path.Combine(path, "review.py") + "\"" + (smoke ? " --self-check" : ""),
            UseShellExecute = false, WorkingDirectory = path, CreateNoWindow = true
        };
    }

    private static void Smoke(string path)
    {
        using (var process = Process.Start(Entry(path, true)))
        {
            if (!process.WaitForExit(105000))
            {
                process.Kill();
                process.WaitForExit();
                throw new InvalidOperationException("新版本自检超时。");
            }
            if (process.ExitCode != 0) throw new InvalidOperationException("新版本未通过本地自检。");
        }
    }

    private static void Launch(string root)
    {
        using (Process.Start(Entry(VersionPath(root, ReadState(root)[0]), false))) { }
    }
}
