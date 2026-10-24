/* Keep the tab icon in sync with the profile photo in the site header. */
(function () {
	'use strict';

	var portrait = document.querySelector('#header .logo .symbol img');
	var icon = document.querySelector('link[rel="icon"]');

	if (!portrait || !icon)
		return;

	var portraitUrl = portrait.currentSrc || portrait.src;

	if (portraitUrl && icon.href !== portraitUrl)
		icon.href = portraitUrl;
})();
