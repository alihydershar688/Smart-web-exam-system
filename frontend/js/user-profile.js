(function () {
    const PROFILE_FIELDS = [
        'id',
        'auth_id',
        'email',
        'role',
        'full_name',
        'first_name',
        'last_name',
        'department',
        'phone',
        'address',
        'bio',
        'batch',
        'student_id',
        'teacher_id',
        'admin_id',
        'profile_photo_url'
    ];

    function readStore(key) {
        return sessionStorage.getItem(key) || localStorage.getItem(key) || '';
    }

    function writeStore(key, value) {
        const next = value == null ? '' : String(value);
        sessionStorage.setItem(key, next);
        localStorage.setItem(key, next);
    }

    function removeStore(key) {
        sessionStorage.removeItem(key);
        localStorage.removeItem(key);
    }

    function clean(value) {
        return (value || '').toString().trim();
    }

    function buildDisplayName(profile) {
        const composed = [clean(profile.first_name), clean(profile.last_name)].filter(Boolean).join(' ');
        return clean(profile.full_name) || composed || clean(profile.email) || 'User';
    }

    function getInitials(name) {
        const parts = clean(name)
            .split(/\s+/)
            .filter(Boolean)
            .slice(0, 2);
        const initials = parts.map((part) => part[0] ? part[0].toUpperCase() : '').join('');
        return initials || 'SE';
    }

    function getRoleLabel(role) {
        const normalized = clean(role).toLowerCase();
        if (normalized === 'teacher') return 'Teacher';
        if (normalized === 'student') return 'Student';
        if (normalized === 'admin') return 'Administrator';
        return 'User';
    }

    function getProfileMeta(profile, fallback) {
        const source = profile || {};
        const email = clean(source.email);
        const roleLabel = clean(source.roleLabel) || getRoleLabel(source.role);
        return email || roleLabel || clean(fallback) || 'Account';
    }

    function getStoredProfile() {
        const profile = {
            id: clean(readStore('userId')),
            email: clean(readStore('userEmail')),
            role: clean(readStore('userRole')),
            first_name: clean(readStore('userFirstName')),
            last_name: clean(readStore('userLastName')),
            department: clean(readStore('userDepartment')),
            phone: clean(readStore('userPhone')),
            address: clean(readStore('userAddress')),
            bio: clean(readStore('userBio')),
            batch: clean(readStore('userBatch')),
            student_id: clean(readStore('studentId')),
            teacher_id: clean(readStore('teacherId')),
            admin_id: clean(readStore('adminId')),
            profile_photo_url: clean(readStore('userProfilePhotoUrl'))
        };
        profile.full_name = buildDisplayName(profile);
        profile.displayName = profile.full_name;
        profile.initials = getInitials(profile.displayName);
        profile.roleLabel = getRoleLabel(profile.role);
        return profile;
    }

    function syncProfile(profile) {
        const merged = {
            ...getStoredProfile(),
            ...(profile || {})
        };

        merged.first_name = clean(merged.first_name);
        merged.last_name = clean(merged.last_name);
        merged.email = clean(merged.email).toLowerCase();
        merged.role = clean(merged.role).toLowerCase();
        merged.full_name = buildDisplayName(merged);
        merged.displayName = merged.full_name;
        merged.initials = getInitials(merged.displayName);
        merged.roleLabel = getRoleLabel(merged.role);

        writeStore('userId', clean(merged.id));
        writeStore('userEmail', merged.email);
        writeStore('userRole', merged.role);
        writeStore('userName', merged.displayName);
        writeStore('userFirstName', merged.first_name);
        writeStore('userLastName', merged.last_name);
        writeStore('userDepartment', clean(merged.department));
        writeStore('userPhone', clean(merged.phone));
        writeStore('userAddress', clean(merged.address));
        writeStore('userBio', clean(merged.bio));
        writeStore('userBatch', clean(merged.batch));
        writeStore('studentId', clean(merged.student_id));
        writeStore('teacherId', clean(merged.teacher_id));
        writeStore('adminId', clean(merged.admin_id));
        writeStore('userProfilePhotoUrl', clean(merged.profile_photo_url));

        return merged;
    }

    async function fetchProfile(supabaseClient) {
        if (!supabaseClient) {
            return getStoredProfile();
        }

        const stored = getStoredProfile();
        const attempts = [];
        if (stored.id) attempts.push(['id', stored.id]);
        if (stored.email) attempts.push(['email', stored.email]);

        for (const [field, value] of attempts) {
            const response = await supabaseClient
                .from('users')
                .select(PROFILE_FIELDS.join(','))
                .eq(field, value)
                .maybeSingle();

            if (!response.error && response.data) {
                return syncProfile(response.data);
            }
        }

        return stored;
    }

    async function saveProfile(supabaseClient, updates) {
        if (!supabaseClient) {
            throw new Error('Profile save requires an initialized Supabase client.');
        }

        const current = await fetchProfile(supabaseClient);
        if (!current.id) {
            throw new Error('No valid user record found for this session.');
        }

        const payload = {};
        [
            'first_name',
            'last_name',
            'department',
            'phone',
            'address',
            'bio',
            'batch'
        ].forEach((field) => {
            if (Object.prototype.hasOwnProperty.call(updates || {}, field)) {
                payload[field] = clean(updates[field]);
            }
        });

        if (Object.prototype.hasOwnProperty.call(updates || {}, 'profile_photo_url')) {
            payload.profile_photo_url = clean(updates.profile_photo_url);
        }

        if (Object.prototype.hasOwnProperty.call(updates || {}, 'student_id')) {
            payload.student_id = clean(updates.student_id);
        }

        if (Object.prototype.hasOwnProperty.call(updates || {}, 'teacher_id')) {
            payload.teacher_id = clean(updates.teacher_id);
        }

        const nextName = buildDisplayName({
            ...current,
            ...payload
        });
        payload.full_name = nextName;

        const response = await supabaseClient
            .from('users')
            .update(payload)
            .eq('id', current.id)
            .select(PROFILE_FIELDS.join(','))
            .single();

        if (response.error) {
            throw response.error;
        }

        return syncProfile(response.data);
    }

    function setText(id, value) {
        if (!id) return;
        const element = document.getElementById(id);
        if (element) element.textContent = value;
    }

    function resolveAvatarTarget(target) {
        if (!target) return null;
        return typeof target === 'string'
            ? (document.getElementById(target) || document.querySelector(target))
            : target;
    }

    function createAvatarFallback() {
        const fallback = document.createElement('span');
        fallback.className = 'avatar-fallback-glyph';
        fallback.setAttribute('aria-hidden', 'true');
        fallback.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
                <path d="M20 21a8 8 0 0 0-16 0" />
                <circle cx="12" cy="8" r="4" />
            </svg>
        `;
        return fallback;
    }

    function renderAvatar(target, options) {
        if (!target) return;
        const element = resolveAvatarTarget(target);
        if (!element) return;

        const config = options || {};
        const name = clean(config.name) || 'User';
        const initials = clean(config.initials) || getInitials(name);
        const photoUrl = clean(config.photoUrl);

        element.textContent = '';
        element.innerHTML = '';
        element.dataset.initials = initials;
        element.setAttribute('aria-label', `${name} avatar`);
        element.classList.remove('has-avatar-image');
        element.classList.add('has-avatar-fallback');

        if (photoUrl) {
            const img = document.createElement('img');
            img.className = 'avatar-media';
            img.src = photoUrl;
            img.alt = `${name} profile photo`;
            img.loading = 'lazy';
            img.referrerPolicy = 'no-referrer';
            img.addEventListener('error', function () {
                renderAvatar(element, { name, initials, photoUrl: '' });
            }, { once: true });
            element.appendChild(img);
            element.classList.add('has-avatar-image');
            element.classList.remove('has-avatar-fallback');
            return;
        }

        element.appendChild(createAvatarFallback());
    }

    function setAvatar(target, value) {
        renderAvatar(target, { initials: value, name: value });
    }

    function applyIdentity(config) {
        const options = config || {};
        const profile = options.profile || getStoredProfile();
        const name = options.name || profile.displayName || 'User';
        const meta = options.meta || profile.roleLabel || 'User';
        const avatar = options.avatar || profile.initials || getInitials(name);
        const photoUrl = options.photoUrl || clean(profile.profile_photo_url);

        (options.nameIds || []).forEach((id) => setText(id, name));
        (options.metaIds || []).forEach((id) => setText(id, meta));
        (options.avatarTargets || []).forEach((target) => renderAvatar(target, {
            name,
            initials: avatar,
            photoUrl
        }));

        return { ...profile, displayName: name, initials: avatar, roleLabel: meta, profile_photo_url: photoUrl };
    }

    function clearProfileStorage() {
        [
            'userId',
            'userEmail',
            'userRole',
            'userName',
            'userFirstName',
            'userLastName',
            'userDepartment',
            'userPhone',
            'userAddress',
            'userBio',
            'userBatch',
            'studentId',
            'teacherId',
            'adminId',
            'userProfilePhotoUrl'
        ].forEach(removeStore);
    }

    window.UserProfile = {
        fields: PROFILE_FIELDS.slice(),
        getInitials,
        getRoleLabel,
        getProfileMeta,
        getStoredProfile,
        syncProfile,
        fetchProfile,
        saveProfile,
        renderAvatar,
        applyIdentity,
        clearProfileStorage
    };
})();
