package workflow

import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.time.Instant

class Workflow {
    static final List<String> ROLES = ['REQUESTER', 'SUPERVISOR', 'MANAGER', 'FINANCE', 'IT'].asImmutable()
    static final List<String> STATUSES = ['DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'].asImmutable()
    private final File directory

    Workflow(File directory) { this.directory = directory }

    /** No state is published until validation, all rules and message generation succeed. */
    Map apply(Map state, Map request) {
        def next = copy(state)
        def rules = new RuleSet(directory)
        def actor = request.actor
        if (!(actor instanceof Map) || !text(actor.id) || !(actor.role in ROLES)) {
            throw new SecurityException('A nonblank actor ID and a supported role are required')
        }
        Map form
        String action
        String previous
        if (request.operation == 'create') {
            def input = request.form
            if (!(input instanceof Map) || !(input.id instanceof String) ||
                    !(input.id ==~ /[A-Za-z0-9_-]{1,64}/) || !text(input.title) || input.title.size() > 200) {
                throw new IllegalArgumentException('Form requires an ID and a title of 1 to 200 characters')
            }
            if (next.forms.containsKey(input.id)) throw new IllegalArgumentException("Duplicate form ID: ${input.id}")
            if (!(input.amount instanceof String)) {
                throw new IllegalArgumentException('Amount must be a quoted decimal string, for example \"6000.00\"')
            }
            BigDecimal amount
            try { amount = new BigDecimal(input.amount.toString()) }
            catch (Exception ignored) { throw new IllegalArgumentException('Amount must be a decimal number') }
            if (amount < 0 || amount.stripTrailingZeros().scale() > 2) {
                throw new IllegalArgumentException('Amount must be nonnegative with at most two decimal places')
            }
            form = [id:input.id, title:input.title, type:input.type, amount:amount.setScale(2),
                    requester:actor.id, status:'DRAFT', route:[], step:0, history:[]]
            route(rules, form) // Validate type and amount now, but select the final route on submission.
            action = 'create'
            previous = null
        } else if (request.operation == 'action') {
            form = next.forms[request.formId]
            if (!form) throw new IllegalArgumentException("Unknown form: ${request.formId}")
            action = request.action
            previous = form.status
            def status = rules.call('transitions', form, action)
            if (!(status instanceof String) || !(status in STATUSES)) {
                throw new IllegalArgumentException('Transition rule returned an unsupported status')
            }
            def allowed = rules.call('permissions', form, action, actor)
            if (!(allowed instanceof Boolean) || !allowed) throw new SecurityException("Not permitted to ${action} this form")
            if (action == 'submit') form.route = route(rules, form)
            if (action == 'approve') form.step++
            form.status = status
        } else {
            throw new IllegalArgumentException("Unknown operation: ${request.operation}")
        }
        if (action == 'create') {
            def allowed = rules.call('permissions', form, action, actor)
            if (!(allowed instanceof Boolean) || !allowed) throw new SecurityException('Not permitted to create this form')
        }
        def now = Instant.now().toString()
        form.history << [action:action, actor:actor.id, role:actor.role, from:previous, to:form.status, at:now]
        def messages = rules.call('notifications', form, action)
        if (!(messages instanceof List) || messages.empty || messages.any {
            !(it instanceof Map) || !text(it.recipient) || !text(it.message)
        }) throw new IllegalArgumentException('Notification rule must return recipient/message maps')
        messages.each { message ->
            next.notifications << [id:UUID.randomUUID().toString(), formId:form.id, at:now,
                                   recipient:message.recipient, message:message.message]
        }
        next.forms[form.id] = form
        state.clear()
        state.putAll(next)
        return copy(form)
    }

    private static List route(RuleSet rules, Map form) {
        def result = rules.call('routing', form)
        if (!(result instanceof List) || result.empty || result.unique(false).size() != result.size() ||
                result.any { !(it in ROLES) || it == 'REQUESTER' }) {
            throw new IllegalArgumentException('Routing rule must return distinct supported reviewer roles')
        }
        new ArrayList(result)
    }

    private static boolean text(Object value) { value instanceof String && !value.trim().empty }
    private static Map copy(Map value) { (Map) new JsonSlurper().parseText(JsonOutput.toJson(value)) }
}
