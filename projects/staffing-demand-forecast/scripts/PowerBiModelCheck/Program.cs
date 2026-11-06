using Microsoft.AnalysisServices.Tabular;

// Microsoft's Tabular Object Model parses the real semantic model offline.
// This checks metadata, not DAX execution or Desktop rendering.
if (args.Length != 1) throw new ArgumentException("Pass the path to model.bim");
var database = JsonSerializer.DeserializeDatabase(File.ReadAllText(args[0]));
var model = database.Model;
if (model.Tables.Count != 6 || model.Relationships.Count != 8)
    throw new InvalidOperationException("Expected six tables and eight relationships");
var measures = model.Tables.Sum(t => t.Measures.Count);
if (measures != 17) throw new InvalidOperationException("Expected 17 DAX measures");
foreach (SingleColumnRelationship r in model.Relationships)
{
    if (r.FromColumn == null || r.ToColumn == null)
        throw new InvalidOperationException($"Unresolved relationship: {r.Name}");
}
Console.WriteLine($"Microsoft TOM parsed {model.Tables.Count} tables, {model.Relationships.Count} relationships and {measures} measures");
