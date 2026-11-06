return { form, action, actor ->
    if (action in ['create', 'submit', 'cancel']) {
        return actor.role == 'REQUESTER' && actor.id == form.requester
    }
    if (action in ['approve', 'reject']) {
        return actor.id != form.requester && actor.role == form.route[form.step]
    }
    return false
}
