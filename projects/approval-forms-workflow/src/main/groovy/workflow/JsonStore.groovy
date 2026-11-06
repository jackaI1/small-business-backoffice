package workflow

import groovy.json.JsonOutput
import groovy.json.JsonSlurper
import java.nio.channels.FileChannel
import java.nio.channels.OverlappingFileLockException
import java.nio.file.Files
import java.nio.file.StandardCopyOption
import java.nio.file.StandardOpenOption

class JsonStore {
    private final File file
    JsonStore(File file) { this.file = file.absoluteFile }

    Object access(boolean write, Closure operation) {
        Files.createDirectories(file.parentFile.toPath())
        def channel = FileChannel.open(new File(file.path + '.lock').toPath(),
            StandardOpenOption.CREATE, StandardOpenOption.WRITE)
        def lock
        def temporary
        try {
            try { lock = channel.tryLock() }
            catch (OverlappingFileLockException ignored) { throw new IOException('Store is busy; retry after the active command finishes') }
            if (lock == null) throw new IOException('Store is busy; retry after the active command finishes')
            def state = file.exists() ? new JsonSlurper().parse(file) : [forms:[:], notifications:[]]
            if (!(state instanceof Map) || !(state.forms instanceof Map) || !(state.notifications instanceof List)) {
                throw new IllegalArgumentException('Invalid saved state: expected forms map and notifications list')
            }
            def result = operation.call(state)
            if (write) {
                temporary = Files.createTempFile(file.parentFile.toPath(), '.forms-', '.tmp')
                Files.writeString(temporary, JsonOutput.prettyPrint(JsonOutput.toJson(state)) + '\n')
                Files.move(temporary, file.toPath(), StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING)
            }
            return result
        } finally {
            try { if (temporary != null) Files.deleteIfExists(temporary) }
            finally {
                try { if (lock != null) lock.release() }
                finally { channel.close() }
            }
        }
    }
}
