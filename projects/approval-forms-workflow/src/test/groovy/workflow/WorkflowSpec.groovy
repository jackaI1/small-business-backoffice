package workflow

import spock.lang.Specification
import spock.lang.TempDir

class WorkflowSpec extends Specification {
    @TempDir File temp
    def engine = new Workflow(new File('rules'))
    Map state = [forms: [:], notifications: []]
    Map owner = [id: 'requester-1', role: 'REQUESTER']

    Map create(String type = 'purchase', Object amount = '6000', String id = 'FORM-1') {
        engine.apply(state, [operation: 'create', actor: owner,
            form: [id: id, title: 'Shared lab supplies', type: type, amount: amount]])
    }
    Map act(String action, Map actor = owner) {
        engine.apply(state, [operation: 'action', formId: 'FORM-1', action: action, actor: actor])
    }

    def 'routes #type amount #amount through #route'() {
        given:
        create(type, amount)
        when:
        def result = act('submit')
        then:
        result.status == 'PENDING'
        result.route == route
        state.notifications.last().recipient == "role:${route.first()}".toString()
        where:
        type       | amount    | route
        'purchase' | '0'       | ['SUPERVISOR']
        'purchase' | '500'     | ['SUPERVISOR']
        'purchase' | '500.01'  | ['MANAGER']
        'purchase' | '5000'    | ['MANAGER']
        'purchase' | '5000.01' | ['MANAGER', 'FINANCE']
        'expense'  | '0'       | ['MANAGER']
        'expense'  | '100'     | ['MANAGER']
        'expense'  | '100.01'  | ['MANAGER', 'FINANCE']
        'access'   | '0'       | ['IT']
    }

    def 'rejects invalid form #type #amount without changing state'() {
        given:
        def before = state.toMapString()
        when:
        create(type, amount)
        then:
        thrown(IllegalArgumentException)
        state.toMapString() == before
        where:
        type       | amount
        'unknown'  | '100'
        'purchase' | '-0.01'
        'purchase' | '1.001'
        'purchase' | 'NaN'
        'purchase' | null
        'access'   | '1'
    }

    def 'rejects every unsupported status and action pair: #status #action'() {
        given:
        create()
        state.forms['FORM-1'].status = status
        def before = state.toMapString()
        when:
        act(action)
        then:
        thrown(IllegalArgumentException)
        state.toMapString() == before
        where:
        [status, action] << [
            ['DRAFT', 'PENDING', 'APPROVED', 'REJECTED', 'CANCELLED'],
            ['submit', 'approve', 'reject', 'cancel', 'reopen']
        ].combinations().findAll { pair ->
            !(pair[0] == 'DRAFT' && pair[1] in ['submit', 'cancel']) &&
            !(pair[0] == 'PENDING' && pair[1] in ['approve', 'reject', 'cancel'])
        }
    }

    def 'requires ordered approvals and records an audit and final requester message'() {
        given:
        create()
        act('submit')
        when:
        def first = act('approve', [id: 'manager-1', role: 'MANAGER'])
        then:
        first.status == 'PENDING'
        first.step == 1
        state.notifications.last().recipient == 'role:FINANCE'
        when:
        def last = act('approve', [id: 'finance-1', role: 'FINANCE'])
        then:
        last.status == 'APPROVED'
        last.history*.action == ['create', 'submit', 'approve', 'approve']
        last.history*.actor == ['requester-1', 'requester-1', 'manager-1', 'finance-1']
        state.notifications.last().recipient == 'user:requester-1'
        state.notifications.last().message.contains('APPROVED')
        state.notifications.last().message.contains('FORM-1')
    }

    def 'denies #action by #actor on #status'() {
        given:
        create()
        if (status == 'PENDING') act('submit')
        def before = state.toMapString()
        when:
        act(action, actor)
        then:
        thrown(SecurityException)
        state.toMapString() == before
        where:
        status    | action    | actor
        'DRAFT'   | 'submit'  | [id: 'other', role: 'REQUESTER']
        'DRAFT'   | 'cancel'  | [id: 'other', role: 'MANAGER']
        'PENDING' | 'cancel'  | [id: 'other', role: 'REQUESTER']
        'PENDING' | 'approve' | [id: 'finance-1', role: 'FINANCE']
        'PENDING' | 'reject'  | [id: 'other', role: 'IT']
        'PENDING' | 'approve' | [id: 'requester-1', role: 'MANAGER']
        'PENDING' | 'approve' | [id: '', role: 'MANAGER']
        'PENDING' | 'approve' | [id: 'other', role: 'ADMIN']
    }

    def 'each routed role can approve its assigned form: #role'() {
        given:
        create(type, amount)
        act('submit')
        when:
        def form = act('approve', [id: 'reviewer-1', role: role])
        then:
        form.status == 'APPROVED'
        where:
        type       | amount | role
        'purchase' | '500'  | 'SUPERVISOR'
        'purchase' | '501'  | 'MANAGER'
        'access'   | '0'    | 'IT'
    }

    def 'reject and cancel notify requester: #action from #status'() {
        given:
        create()
        if (status == 'PENDING') act('submit')
        when:
        def result = act(action, actor)
        then:
        result.status == expected
        state.notifications.last().recipient == 'user:requester-1'
        state.notifications.last().message.contains(expected)
        where:
        status    | action   | actor                               | expected
        'DRAFT'   | 'cancel' | [id:'requester-1', role:'REQUESTER'] | 'CANCELLED'
        'PENDING' | 'cancel' | [id:'requester-1', role:'REQUESTER'] | 'CANCELLED'
        'PENDING' | 'reject' | [id:'manager-1', role:'MANAGER']     | 'REJECTED'
    }

    def 'duplicate IDs and unknown forms never overwrite records'() {
        given:
        create()
        def before = state.toMapString()
        when:
        create()
        then:
        thrown(IllegalArgumentException)
        state.toMapString() == before
        when:
        engine.apply(state, [operation:'action', formId:'missing', action:'submit', actor:owner])
        then:
        thrown(IllegalArgumentException)
        state.toMapString() == before
    }

    def 'reloads owner edits but preserves the route of a submitted form'() {
        given:
        new File('rules').eachFile { new File(temp, it.name).text = it.text }
        engine = new Workflow(temp)
        create()
        act('submit')
        new File(temp, 'routing.groovy').text = "return { form -> ['IT'] }"
        when:
        act('approve', [id:'manager-1', role:'MANAGER'])
        then:
        state.forms['FORM-1'].route == ['MANAGER', 'FINANCE']
        when:
        create('purchase', '6000', 'FORM-2')
        def second = engine.apply(state, [operation:'action', formId:'FORM-2', action:'submit', actor:owner])
        then:
        second.route == ['IT']
        when:
        new File(temp, 'permissions.groovy').text = 'return { form, action, actor -> false }'
        act('approve', [id:'finance-1', role:'FINANCE'])
        then:
        thrown(SecurityException)
    }

    def 'transition and notification edits take effect on the next command'() {
        given:
        new File('rules').eachFile { new File(temp, it.name).text = it.text }
        engine = new Workflow(temp)
        create()
        new File(temp, 'transitions.groovy').text = "return { f, a -> 'REJECTED' }"
        new File(temp, 'notifications.groovy').text =
            "return { f, a -> [[recipient:'user:' + f.requester, message:'Policy review: ' + f.status]] }"
        when:
        def result = act('submit')
        then:
        result.status == 'REJECTED'
        state.notifications.last().message == 'Policy review: REJECTED'
    }

    def 'missing rule file fails without changing state'() {
        given:
        new File('rules').eachFile { new File(temp, it.name).text = it.text }
        engine = new Workflow(temp)
        create()
        def before = state.toMapString()
        new File(temp, 'permissions.groovy').delete()
        when:
        act('submit')
        then:
        def error = thrown(IllegalArgumentException)
        error.message.contains('Missing rule file')
        state.toMapString() == before
    }

    def 'requires a requester identity to create a form: #actor'() {
        when:
        engine.apply(state, [operation:'create', actor:actor,
            form:[id:'X', title:'Lab supplies', type:'purchase', amount:'10']])
        then:
        thrown(SecurityException)
        state.forms.isEmpty()
        state.notifications.empty
        where:
        actor << [null, [:], [id:'',role:'REQUESTER'], [id:'r',role:'ADMIN'], [id:'r',role:'MANAGER']]
    }

    def 'validates form identifiers and titles before saving: #id #title'() {
        when:
        engine.apply(state, [operation:'create', actor:owner,
            form:[id:id, title:title, type:'purchase', amount:'10']])
        then:
        thrown(IllegalArgumentException)
        state.forms.isEmpty()
        state.notifications.empty
        where:
        id          | title
        null        | 'Lab supplies'
        '../escape' | 'Lab supplies'
        'X'         | '   '
        'X'         | null
        'X'         | ('a' * 201)
    }

    def 'broken or malformed rules fail without partial state changes: #file'() {
        given:
        new File('rules').eachFile { new File(temp, it.name).text = it.text }
        engine = new Workflow(temp)
        create()
        def before = state.toMapString()
        new File(temp, file).text = replacement
        when:
        act('submit')
        then:
        thrown(RuntimeException)
        state.toMapString() == before
        where:
        file                    | replacement
        'routing.groovy'        | "return { f -> [] }"
        'routing.groovy'        | "return { f -> ['ADMIN'] }"
        'routing.groovy'        | "return { f -> ['MANAGER', 'MANAGER'] }"
        'routing.groovy'        | "return { f -> ['REQUESTER'] }"
        'routing.groovy'        | 'return 42'
        'transitions.groovy'    | "return { f, a -> 'SURPRISE' }"
        'permissions.groovy'    | "return { f, a, u -> 'yes' }"
        'notifications.groovy'  | "return { f, a -> null }"
        'notifications.groovy'  | 'not valid groovy @'
    }
}
