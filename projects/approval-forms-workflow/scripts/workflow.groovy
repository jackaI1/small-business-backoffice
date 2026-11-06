import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import workflow.Runner

try {
    if (args.length != 3) throw new IllegalArgumentException('Usage: workflow.groovy <request.json> <store.json> <rules-directory>')
    def request = new JsonSlurper().parse(new File(args[0]))
    if (!(request instanceof Map)) throw new IllegalArgumentException('Request must be a JSON object')
    def result = Runner.execute(request, new File(args[1]), new File(args[2]))
    println JsonOutput.prettyPrint(JsonOutput.toJson(result))
} catch (Exception error) {
    System.err.println("Workflow error: ${error.message}")
    System.exit(1)
}
