import groovy.json.JsonSlurper
import workflow.Runner
import java.nio.file.Files

// Each run owns a new directory. Never reset an existing store to run the demo.
def directory = Files.createTempDirectory('approval-workflow-demo-').toFile()
try {
    def store = new File(directory, 'forms.json')
    def rules = new File('rules')
    ['create', 'submit'].each { name ->
        def request = new JsonSlurper().parse(new File("examples/${name}.json"))
        def result = Runner.execute(request, store, rules)
        println "${name}: ${result.id} -> ${result.status}, reviewers=${result.route}"
    }
    try {
        Runner.execute([operation:'action', formId:'LAB-001', action:'approve',
            actor:[id:'it-reviewer', role:'IT']], store, rules)
        throw new IllegalStateException('Expected the wrong-role approval to be denied')
    } catch (SecurityException expected) {
        println "Blocked wrong-role approval: ${expected.message}"
    }
    ['approve-manager', 'approve-finance'].each { name ->
        def request = new JsonSlurper().parse(new File("examples/${name}.json"))
        def result = Runner.execute(request, store, rules)
        println "${name}: ${result.id} -> ${result.status}"
    }
    def form = Runner.execute([operation:'show', formId:'LAB-001'], store, rules)
    assert form.status == 'APPROVED'
    assert form.history*.action == ['create','submit','approve','approve']
    println 'Saved decisions:'
    form.history.each { println "  ${it.actor} (${it.role}): ${it.action} -> ${it.to}" }
    def outbox = Runner.execute([operation:'outbox'], store, rules)
    assert outbox.size() == 6
    println "Saved outbox: ${outbox.size()} messages (no email sent)"
    outbox.each { println "  ${it.recipient}: ${it.message}" }
} finally {
    if (!directory.deleteDir()) throw new IOException("Cannot clean up demo directory: ${directory}")
}
println 'Demo temporary files removed.'
