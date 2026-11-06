// These messages go into the saved outbox; this script does not send email.
return { form, action ->
    def messages = [[recipient: "user:${form.requester}".toString(),
        message: "${form.id}: ${form.title} is ${form.status} after ${action}.".toString()]]
    if (form.status == 'PENDING') {
        messages << [recipient: "role:${form.route[form.step]}".toString(),
            message: "Review ${form.id}: ${form.title} (${form.type}, CAD ${form.amount}).".toString()]
    }
    return messages
}
