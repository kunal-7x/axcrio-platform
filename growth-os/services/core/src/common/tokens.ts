/**
 * DI tokens for non-class providers (config, bus). Symbols avoid name collisions and make
 * the dependency explicit at the injection site.
 */
export const CONFIG = Symbol('CORE_CONFIG');
export const EVENT_BUS = Symbol('EVENT_BUS');
