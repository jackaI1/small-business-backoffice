package workflow

/** Trusted owner-maintained scripts, reloaded for each operation. */
class RuleSet {
    private final Map<String, Closure> functions = [:]

    RuleSet(File directory) {
        ['routing', 'transitions', 'permissions', 'notifications'].each { name ->
            def file = new File(directory, "${name}.groovy")
            if (!file.isFile()) throw new IllegalArgumentException("Missing rule file: ${file}")
            def result = new GroovyShell(getClass().classLoader).evaluate(file)
            if (!(result instanceof Closure)) throw new IllegalArgumentException("${name} must return a closure")
            functions[name] = result
        }
    }

    Object call(String name, Object... args) { functions[name].call(*args) }
}
