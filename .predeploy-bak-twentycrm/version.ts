// Single source of truth for the app version shown bottom-right in the panel.
// Bump APP_VERSION on each release, OR set NEXT_PUBLIC_APP_VERSION at build time
// (deploy/Dockerfile.frontend passes it as a build ARG) to override without a code
// change. The badge updates the moment a new build ships with a new value.
export const APP_VERSION =
    (typeof process !== "undefined" && process.env.NEXT_PUBLIC_APP_VERSION) || "1.4.0";
