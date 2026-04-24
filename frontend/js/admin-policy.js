;(function () {
    if (window.AdminPolicy) return

    const POLICY = {
        primaryAdminEmail: 'alihydershar688@gmail.com',
        primaryAdminId: 'A2024001',
        authorizedAdminEmails: ['alihydershar688@gmail.com'],
        authorizedAdminIds: ['A2024001']
    }

    function normalize(value) {
        return (value || '').toString().trim().toLowerCase()
    }

    window.AdminPolicy = {
        config: POLICY,
        isAuthorizedAdmin(user) {
            const role = normalize(user?.role)
            const email = normalize(user?.email)
            const adminId = normalize(user?.admin_id || user?.adminId)
            if (role !== 'admin') return false
            if (POLICY.authorizedAdminEmails.map(normalize).includes(email)) return true
            if (POLICY.authorizedAdminIds.map(normalize).includes(adminId)) return true
            return false
        },
        getSummary() {
            return {
                primaryAdminEmail: POLICY.primaryAdminEmail,
                primaryAdminId: POLICY.primaryAdminId,
                authorizedAdminEmails: [...POLICY.authorizedAdminEmails],
                authorizedAdminIds: [...POLICY.authorizedAdminIds]
            }
        }
    }
})()
