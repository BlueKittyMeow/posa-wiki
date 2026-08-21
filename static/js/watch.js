/* Watch page: YouTube IFrame player + night-friendly dim overlay.
 *
 * The video id is never concatenated into this script -- it is read from the
 * data-video-id attribute the template renders (Jinja-escaped).
 *
 * Dim levels are opacity values for a pure-black overlay that covers ONLY the
 * player. The overlay never pauses anything: at 100% the picture is hidden and
 * the audio keeps going, which is the whole point (listening from bed).
 */
(function () {
    'use strict';

    var DIM_LEVELS = [0, 0.5, 0.75, 1];
    var DIM_KEY = 'posa-wiki-watch-dim';
    var NIGHT_KEY = 'posa-wiki-watch-night';

    var page = document.querySelector('.watch-page');
    if (!page) { return; }

    var videoId = page.getAttribute('data-video-id');
    var overlay = document.getElementById('watch-overlay');
    var nightBtn = document.getElementById('watch-night-btn');
    var dimButtons = Array.prototype.slice.call(
        document.querySelectorAll('.watch-dim-btn'));

    var player = null;
    var dimIndex = 0;
    var night = false;

    function store(key, value) {
        try { localStorage.setItem(key, value); } catch (e) { /* private mode */ }
    }

    function load(key) {
        try { return localStorage.getItem(key); } catch (e) { return null; }
    }

    function applyDim() {
        var level = DIM_LEVELS[dimIndex];
        overlay.style.opacity = String(level);
        // Bright must not swallow clicks meant for the player; every dimmed
        // state turns the overlay into one huge tap target.
        overlay.style.pointerEvents = level === 0 ? 'none' : 'auto';
        dimButtons.forEach(function (btn) {
            var active = parseFloat(btn.getAttribute('data-dim')) === level;
            btn.classList.toggle('is-active', active);
            btn.setAttribute('aria-pressed', active ? 'true' : 'false');
        });
        store(DIM_KEY, String(dimIndex));
    }

    function setDim(index) {
        dimIndex = ((index % DIM_LEVELS.length) + DIM_LEVELS.length) % DIM_LEVELS.length;
        applyDim();
    }

    function cycleDim() { setDim(dimIndex + 1); }

    function applyNight() {
        document.body.classList.toggle('watch-night', night);
        nightBtn.classList.toggle('is-active', night);
        nightBtn.setAttribute('aria-pressed', night ? 'true' : 'false');
        store(NIGHT_KEY, night ? '1' : '0');
    }

    function toggleNight() { night = !night; applyNight(); }

    function togglePlay() {
        if (!player || typeof player.getPlayerState !== 'function') { return; }
        if (player.getPlayerState() === 1) {  // YT.PlayerState.PLAYING
            player.pauseVideo();
        } else {
            player.playVideo();
        }
    }

    dimButtons.forEach(function (btn) {
        btn.addEventListener('click', function () {
            setDim(DIM_LEVELS.indexOf(parseFloat(btn.getAttribute('data-dim'))));
        });
    });

    nightBtn.addEventListener('click', toggleNight);

    overlay.addEventListener('click', cycleDim);
    overlay.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            cycleDim();
        }
    });

    document.addEventListener('keydown', function (event) {
        var tag = (event.target && event.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea' || tag === 'select') { return; }
        if (event.metaKey || event.ctrlKey || event.altKey) { return; }

        if (event.key === 'd' || event.key === 'D') {
            event.preventDefault();
            cycleDim();
        } else if (event.key === 'n' || event.key === 'N') {
            event.preventDefault();
            toggleNight();
        } else if (event.key === ' ' && event.target === document.body) {
            event.preventDefault();
            togglePlay();
        }
    });

    // Restore the last-used mood.
    var savedDim = parseInt(load(DIM_KEY), 10);
    if (!isNaN(savedDim)) { dimIndex = savedDim; }
    night = load(NIGHT_KEY) === '1';
    applyDim();
    applyNight();

    // The IFrame API calls this global once https://www.youtube.com/iframe_api
    // has loaded.
    window.onYouTubeIframeAPIReady = function () {
        if (!videoId || typeof YT === 'undefined' || !YT.Player) { return; }
        player = new YT.Player('watch-player', {
            videoId: videoId,
            playerVars: {
                enablejsapi: 1,
                playsinline: 1,
                rel: 0,
                modestbranding: 1
            }
        });
    };
}());
