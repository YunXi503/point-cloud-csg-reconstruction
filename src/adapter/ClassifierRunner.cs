using System;
using System.IO;
using System.Globalization;
using System.Linq;
using System.Reflection;
using System.Text;

// Calls the existing classifier API without invoking its hard-coded desktop Main.
internal static class ClassifierRunner
{
    private static int Main(string[] args)
    {
        Console.OutputEncoding = new UTF8Encoding(false);
        if (args.Length != 3)
        {
            Console.Error.WriteLine("Usage: ClassifierRunner classifier.dll point-normals.csv new-output.csv");
            return 2;
        }
        try
        {
            string assemblyPath = Path.GetFullPath(args[0]);
            string inputPath = Path.GetFullPath(args[1]);
            string outputPath = Path.GetFullPath(args[2]);
            if (!File.Exists(assemblyPath) || !File.Exists(inputPath))
                throw new FileNotFoundException("Classifier assembly or input CSV was not found.");
            if (File.Exists(outputPath))
                throw new IOException("Output already exists; choose a new run directory.");
            if (CultureInfo.CurrentCulture.NumberFormat.NumberDecimalSeparator != ".")
                throw new InvalidOperationException("The preserved CSV algorithms require a decimal-point culture. Current culture: " + CultureInfo.CurrentCulture.Name);
            Directory.CreateDirectory(Path.GetDirectoryName(outputPath));
            var assembly = Assembly.LoadFrom(assemblyPath);
            var candidates = assembly.GetTypes().Where(type =>
                type.IsPublic && type.Name == "FeatureClassifier" &&
                type.GetMethod("Execute", new[] { typeof(string), typeof(string) }) != null).ToArray();
            if (candidates.Length != 1)
                throw new InvalidOperationException("Expected exactly one public FeatureClassifier.Execute(string, string).");
            Console.WriteLine("Runtime: " + Environment.Version.ToString());
            Console.WriteLine("Culture: " + CultureInfo.CurrentCulture.Name);
            Console.WriteLine("Invoking unchanged classifier: " + candidates[0].FullName);
            var classifier = Activator.CreateInstance(candidates[0]);
            candidates[0].GetMethod("Execute", new[] { typeof(string), typeof(string) })
                .Invoke(classifier, new object[] { inputPath, outputPath });
            if (!File.Exists(outputPath))
                throw new IOException("The research classifier did not create an output CSV.");
            return 0;
        }
        catch (Exception error)
        {
            Console.Error.WriteLine((error.InnerException ?? error).ToString());
            return 1;
        }
    }
}
