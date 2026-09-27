/**
 * Hand-written structural validators (no eval, no dynamic code). Each validator is a plain
 * function `(value, path) => typed value` that throws a `ValidationError` naming the path of
 * the first violation. Objects are strict: required keys must be present, unknown keys are
 * rejected unless the schema allows them, enums and id patterns are checked.
 */

export class ValidationError extends Error {
  override name = 'ValidationError';
  readonly path: string;
  constructor(path: string, message: string) {
    super(`${path}: ${message}`);
    this.path = path;
  }
}

export type Validator<T> = (x: unknown, path: string) => T;

export function str(opts: { pattern?: RegExp; maxLength?: number; minLength?: number } = {}): Validator<string> {
  return (x, path) => {
    if (typeof x !== 'string') throw new ValidationError(path, 'expected a string');
    if (opts.pattern && !opts.pattern.test(x)) throw new ValidationError(path, `does not match ${opts.pattern.source}`);
    if (opts.maxLength !== undefined && x.length > opts.maxLength) throw new ValidationError(path, `longer than ${opts.maxLength}`);
    if (opts.minLength !== undefined && x.length < opts.minLength) throw new ValidationError(path, `shorter than ${opts.minLength}`);
    return x;
  };
}

export function num(opts: { min?: number; max?: number } = {}): Validator<number> {
  return (x, path) => {
    if (typeof x !== 'number' || !Number.isFinite(x)) throw new ValidationError(path, 'expected a finite number');
    if (opts.min !== undefined && x < opts.min) throw new ValidationError(path, `below minimum ${opts.min}`);
    if (opts.max !== undefined && x > opts.max) throw new ValidationError(path, `above maximum ${opts.max}`);
    return x;
  };
}

export function int(opts: { min?: number; max?: number } = {}): Validator<number> {
  const n = num(opts);
  return (x, path) => {
    const v = n(x, path);
    if (!Number.isInteger(v)) throw new ValidationError(path, 'expected an integer');
    return v;
  };
}

export const bool: Validator<boolean> = (x, path) => {
  if (typeof x !== 'boolean') throw new ValidationError(path, 'expected a boolean');
  return x;
};

export const nil: Validator<null> = (x, path) => {
  if (x !== null) throw new ValidationError(path, 'expected null');
  return null;
};

export const any: Validator<unknown> = (x) => x;

export function lit<T extends string | number | boolean>(value: T): Validator<T> {
  return (x, path) => {
    if (x !== value) throw new ValidationError(path, `expected the constant ${JSON.stringify(value)}`);
    return value;
  };
}

export function enumOf<T extends string>(values: readonly T[]): Validator<T> {
  return (x, path) => {
    if (typeof x !== 'string' || !(values as readonly string[]).includes(x)) {
      throw new ValidationError(path, `expected one of ${values.join(', ')}`);
    }
    return x as T;
  };
}

export function nullable<T>(v: Validator<T>): Validator<T | null> {
  return (x, path) => (x === null ? null : v(x, path));
}

export function arr<T>(item: Validator<T>, opts: { min?: number; max?: number } = {}): Validator<T[]> {
  return (x, path) => {
    if (!Array.isArray(x)) throw new ValidationError(path, 'expected an array');
    if (opts.min !== undefined && x.length < opts.min) throw new ValidationError(path, `fewer than ${opts.min} items`);
    if (opts.max !== undefined && x.length > opts.max) throw new ValidationError(path, `more than ${opts.max} items`);
    return x.map((e, i) => item(e, `${path}[${i}]`));
  };
}

export function tuple<A, B>(a: Validator<A>, b: Validator<B>): Validator<[A, B]> {
  return (x, path) => {
    if (!Array.isArray(x) || x.length !== 2) throw new ValidationError(path, 'expected a pair');
    return [a(x[0], `${path}[0]`), b(x[1], `${path}[1]`)];
  };
}

type Shape = Record<string, Validator<unknown>>;
type Out<V> = V extends Validator<infer T> ? T : never;
type Simplify<T> = { [K in keyof T]: T[K] } & {};
type Infer<S extends Shape, O extends keyof S> = Simplify<{ [K in Exclude<keyof S, O>]: Out<S[K]> } & { [K in O]?: Out<S[K]> }>;

export function isPlainObject(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

/**
 * A strict object validator. Every key in `shape` is required unless listed in `optional`.
 * Unknown keys are rejected (additionalProperties: false) unless `additional` is given, in
 * which case unknown keys are validated with it.
 */
export function obj<S extends Shape, O extends keyof S & string = never>(
  shape: S,
  opts: { optional?: readonly O[]; additional?: Validator<unknown> } = {},
): Validator<Infer<S, O>> {
  const optional = new Set<string>(opts.optional ?? []);
  return (x, path) => {
    if (!isPlainObject(x)) throw new ValidationError(path, 'expected an object');
    const out: Record<string, unknown> = {};
    for (const key of Object.keys(shape)) {
      if (!(key in x)) {
        if (optional.has(key)) continue;
        throw new ValidationError(`${path}.${key}`, 'required key missing');
      }
      out[key] = (shape[key] as Validator<unknown>)(x[key], `${path}.${key}`);
    }
    for (const key of Object.keys(x)) {
      if (key in shape) continue;
      if (opts.additional) {
        out[key] = opts.additional(x[key], `${path}.${key}`);
      } else {
        throw new ValidationError(`${path}.${key}`, 'unknown key');
      }
    }
    return out as Infer<S, O>;
  };
}

/** A map with validated values; keys may be constrained by a pattern or an enum. */
export function record<T>(
  value: Validator<T>,
  opts: { keyPattern?: RegExp; keys?: readonly string[]; minProperties?: number } = {},
): Validator<Record<string, T>> {
  return (x, path) => {
    if (!isPlainObject(x)) throw new ValidationError(path, 'expected an object');
    const keys = Object.keys(x);
    if (opts.minProperties !== undefined && keys.length < opts.minProperties) {
      throw new ValidationError(path, `fewer than ${opts.minProperties} keys`);
    }
    const out: Record<string, T> = {};
    for (const k of keys) {
      if (opts.keyPattern && !opts.keyPattern.test(k)) throw new ValidationError(`${path}.${k}`, 'key does not match the pattern');
      if (opts.keys && !opts.keys.includes(k)) throw new ValidationError(`${path}.${k}`, `key not among ${opts.keys.join(', ')}`);
      out[k] = value(x[k], `${path}.${k}`);
    }
    return out;
  };
}

/** Try each alternative; the value must match exactly one (JSON Schema oneOf). */
export function oneOf<T extends unknown[]>(...alts: { [K in keyof T]: Validator<T[K]> }): Validator<T[number]> {
  return (x, path) => {
    const matches: T[number][] = [];
    const errors: string[] = [];
    for (const alt of alts) {
      try {
        matches.push(alt(x, path));
      } catch (e) {
        errors.push(e instanceof Error ? e.message : String(e));
      }
    }
    if (matches.length === 1) return matches[0] as T[number];
    if (matches.length === 0) throw new ValidationError(path, `no alternative matched (${errors.join(' | ')})`);
    throw new ValidationError(path, 'more than one alternative matched');
  };
}

/** Parse JSON text safely and validate it; malformed JSON and structural violations both throw. */
export function parseAndValidate<T>(text: string, v: Validator<T>, root = '$'): T {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch {
    throw new ValidationError(root, 'not valid JSON');
  }
  return v(parsed, root);
}
