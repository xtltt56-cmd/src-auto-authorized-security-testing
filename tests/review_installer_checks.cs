using System;
using System.IO;
using System.IO.Compression;
using System.Security.Cryptography;

internal static class ReviewSetupChecks
{
    private static void Require(bool passed, string label)
    {
        if (!passed) throw new Exception(label);
        Console.WriteLine("PASS " + label);
    }

    private static ReviewSetup.Asset Asset(string zip, string version)
    {
        using (var sha = SHA256.Create())
        using (var file = File.OpenRead(zip))
            return new ReviewSetup.Asset {Version = version, Size = file.Length,
                Digest = BitConverter.ToString(sha.ComputeHash(file)).Replace("-", "")};
    }

    private static string Active(string root)
    {
        return File.ReadAllLines(Path.Combine(root, "active.txt"))[0];
    }

    public static void Main(string[] args)
    {
        string first = args[0], second = args[1], root = args[2];
        Directory.CreateDirectory(root);

        string fixture = @"[
            {""tag_name"":""v99.0.0"",""draft"":false,""prerelease"":false,""assets"":[]},
            {""tag_name"":""review-v99.0.0"",""draft"":false,""prerelease"":true,""assets"":[]},
            {""tag_name"":""review-v0.18.0"",""draft"":false,""prerelease"":false,""assets"":[{
            ""name"":""SRC-Auto-Review-v0.18.0-win-x64.zip"",""size"":123,
            ""browser_download_url"":""https://github.com/xtltt56-cmd/src-auto-authorized-security-testing/releases/download/review-v0.18.0/SRC-Auto-Review-v0.18.0-win-x64.zip"",
            ""digest"":""sha256:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef""}]}]";
        var release = ReviewSetup.ParseReleases(fixture);
        Require(release.Version == "0.18.0" && release.Size == 123, "release selection");

        var firstAsset = Asset(first, "0.18.0");
        ReviewSetup.Install(root, first, firstAsset);
        Require(Active(root) == "0.18.0", "first install with real GUI and Bandit self-check");

        string workspace = Path.Combine(root, "workspace");
        Directory.CreateDirectory(workspace);
        var report = Path.Combine(workspace, "keep.md");
        File.WriteAllText(report, "test data");
        var secondAsset = Asset(second, "0.18.1");
        string digest = secondAsset.Digest;
        secondAsset.Digest = new string('0', 64);
        bool rejected = false;
        try { ReviewSetup.Install(root, second, secondAsset); }
        catch (InvalidDataException) { rejected = true; }
        Require(rejected && Active(root) == "0.18.0" &&
                !Directory.Exists(Path.Combine(root, "versions", "v0.18.1")), "bad digest preserves active install");

        secondAsset.Digest = digest;
        ReviewSetup.Install(root, second, secondAsset);
        Require(Active(root) == "0.18.1" && File.ReadAllText(report) == "test data", "upgrade preserves local files");
        ReviewSetup.Rollback(root);
        Require(Active(root) == "0.18.0" && File.Exists(report), "rollback and local file preservation");

        using (var invalid = new MemoryStream())
        {
            using (var zip = new ZipArchive(invalid, ZipArchiveMode.Create, true))
                zip.CreateEntry("invalid:name.txt");
            invalid.Position = 0;
            rejected = false;
            try { ReviewSetup.Extract(invalid, Path.Combine(root, "empty")); }
            catch (InvalidDataException) { rejected = true; }
            Require(rejected, "reject Windows alternate stream path");
        }
    }
}
