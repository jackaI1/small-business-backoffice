package workflow

import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import spock.lang.Specification
import spock.lang.TempDir
import java.nio.channels.FileChannel
import java.nio.file.StandardOpenOption
import java.nio.file.Files

class PersistenceSpec extends Specification {
    @TempDir File temp
    File store
    File rules = new File('rules')
    Map create = [operation:'create', actor:[id:'requester-1', role:'REQUESTER'],
                  form:[id:'DEMO-1', title:'Lab supplies', type:'purchase', amount:'6000']]
    Map submit = [operation:'action', formId:'DEMO-1', action:'submit', actor:[id:'requester-1',role:'REQUESTER']]

    def setup() { store = new File(temp, 'nested/forms.json') }

    def 'persists forms audit and outbox across fresh invocations'() {
        when:
        Runner.execute(create, store, rules)
        Runner.execute(submit, store, rules)
        def form = Runner.execute([operation:'show', formId:'DEMO-1'], store, rules)
        def messages = Runner.execute([operation:'outbox'], store, rules)
        then:
        form.status == 'PENDING'
        form.route == ['MANAGER','FINANCE']
        form.history*.action == ['create','submit']
        messages*.recipient == ['user:requester-1','user:requester-1','role:MANAGER']
        messages*.id.unique().size() == 3
        new JsonSlurper().parse(store).forms['DEMO-1'].status == 'PENDING'
    }

    def 'denied actions leave saved bytes unchanged'() {
        given:
        Runner.execute(create, store, rules)
        Runner.execute(submit, store, rules)
        def before = store.bytes
        when:
        Runner.execute([operation:'action', formId:'DEMO-1', action:'approve',
                       actor:[id:'other',role:'IT']], store, rules)
        then:
        thrown(SecurityException)
        store.bytes == before
        store.parentFile.list().sort() == ['forms.json','forms.json.lock']
    }

    def 'corrupted saved state is reported and never overwritten: #contents'() {
        given:
        store.parentFile.mkdirs()
        store.text = contents
        when:
        Runner.execute(create, store, rules)
        then:
        thrown(RuntimeException)
        store.text == contents
        where:
        contents << ['{broken', '[]', '{"forms":[],"notifications":[]}']
    }

    def 'overlapping writers fail clearly and the released lock can be reused'() {
        given:
        Runner.execute(create, store, rules)
        def before = store.text
        def channel = FileChannel.open(new File(store.path + '.lock').toPath(), StandardOpenOption.WRITE)
        def lock = channel.lock()
        when:
        Runner.execute(submit, store, rules)
        then:
        def error = thrown(IOException)
        error.message.contains('busy')
        store.text == before
        when:
        lock.release()
        channel.close()
        def result = Runner.execute(submit, store, rules)
        then:
        result.status == 'PENDING'
        cleanup:
        if (lock.valid) lock.release()
        channel.close()
    }

    def 'unknown commands and unknown form reads do not change saved state'() {
        given:
        Runner.execute(create, store, rules)
        def before = store.text
        when:
        Runner.execute([operation:op, formId:'absent'], store, rules)
        then:
        thrown(IllegalArgumentException)
        store.text == before
        where:
        op << ['delete','show']
    }

    def 'real CLI persists a form and returns nonzero for a rejected command'() {
        given:
        def request = new File(temp,'request.json')
        request.text = JsonOutput.toJson(create)
        when:
        def first = cli(request)
        then:
        first.code == 0
        new JsonSlurper().parseText(first.output).status == 'DRAFT'
        when:
        request.text = JsonOutput.toJson(submit)
        def second = cli(request)
        then:
        second.code == 0
        new JsonSlurper().parseText(second.output).status == 'PENDING'
        when:
        def before = store.text
        def third = cli(request)
        then:
        third.code != 0
        third.error.contains('submit')
        store.text == before
    }

    def 'real CLI rejects malformed request JSON without creating a store'() {
        given:
        def request = new File(temp,'bad.json')
        request.text = '{broken'
        when:
        def result = cli(request)
        then:
        result.code != 0
        !store.exists()
    }

    def 'CLI rejects unquoted numeric amount #amount instead of silently narrowing it'() {
        given:
        def request = new File(temp,'large-amount.json')
        request.text = JsonOutput.toJson(create).replace('\"6000\"', amount)
        when:
        def result = cli(request)
        then:
        result.code != 0
        result.error.contains('decimal string')
        !store.exists()
        where:
        amount << ['0', '6000', '18446744073709551617']
    }

    def 'quoted large amounts keep their exact value across saved commands'() {
        given:
        create.form.amount = '18446744073709551617.00'
        when:
        Runner.execute(create, store, rules)
        def result = Runner.execute(submit, store, rules)
        then:
        result.amount.toPlainString() == '18446744073709551617.00'
        result.route == ['MANAGER', 'FINANCE']
    }

    def 'cleanup errors still release the real file lock'() {
        given:
        // Inject only an otherwise hard-to-trigger deletion failure. All I/O and locking remain real.
        Files.metaClass.'static'.deleteIfExists = { java.nio.file.Path ignored ->
            throw new IOException('Simulated temporary-file cleanup failure')
        }
        when:
        Runner.execute(create, store, rules)
        then:
        def error = thrown(IOException)
        error.message.contains('cleanup failure')
        when:
        GroovySystem.metaClassRegistry.removeMetaClass(Files)
        def channel = FileChannel.open(new File(store.path + '.lock').toPath(), StandardOpenOption.WRITE)
        def lock
        try {
            lock = channel.tryLock()
            assert lock != null
        } finally {
            if (lock != null) lock.release()
            channel.close()
        }
        then:
        noExceptionThrown()
        cleanup:
        GroovySystem.metaClassRegistry.removeMetaClass(Files)
    }

    private Map cli(File request) {
        def process = new ProcessBuilder(new File(System.getProperty('java.home'),'bin/java').path,
            '-Xmx128m', '-cp', System.getProperty('workflow.classpath'), 'groovy.ui.GroovyMain',
            'scripts/workflow.groovy', request.path, store.path, rules.path).start()
        try {
            assert process.waitFor(30, java.util.concurrent.TimeUnit.SECONDS)
            [code:process.exitValue(), output:process.inputStream.text, error:process.errorStream.text]
        } finally {
            process.destroy()
            if (process.alive) process.destroyForcibly().waitFor()
        }
    }
}
