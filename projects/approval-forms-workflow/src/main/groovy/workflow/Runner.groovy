package workflow

class Runner {
    static Object execute(Map request, File store, File rules) {
        def operation = request.operation
        if (!(operation in ['create', 'action', 'show', 'outbox'])) {
            throw new IllegalArgumentException("Unknown operation: ${operation}")
        }
        new JsonStore(store).access(operation in ['create','action']) { state ->
            if (operation == 'outbox') return state.notifications
            if (operation == 'show') {
                def form = state.forms[request.formId]
                if (!form) throw new IllegalArgumentException("Unknown form: ${request.formId}")
                return form
            }
            new Workflow(rules).apply(state, request)
        }
    }
}
