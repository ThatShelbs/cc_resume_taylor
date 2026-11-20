/** Text boxes for lists (titles, cities, states) and whole numbers.
 *
 * The raw text lives in local state, so typing a trailing space, a comma or a new line is never
 * undone; the parsed list is reported on every change but the box is only rewritten from the
 * outside when the list it holds no longer matches (a save, or a "suggest from my profile"). */
import { useEffect, useRef, useState } from "react";
import { Input, Textarea } from "@/components/ui/input";

export type ListMode = "lines" | "commas";

export function parseList(raw: string, mode: ListMode = "lines"): string[] {
  const parts = mode === "commas" ? raw.split(/[,\n]/) : raw.split("\n");
  return parts.map((x) => x.trim()).filter(Boolean);
}

export const joinList = (a: string[], mode: ListMode = "lines") => a.join(mode === "commas" ? ", " : "\n");

const same = (a: string[], b: string[]) => a.length === b.length && a.every((x, i) => x === b[i]);

interface ListFieldProps {
  value: string[];
  onChange: (next: string[]) => void;
  mode?: ListMode;
  /** One line (Input) instead of a Textarea. */
  single?: boolean;
  rows?: number;
  placeholder?: string;
  className?: string;
  "aria-label": string;
  /** Applied to each item after parsing (for example upper-casing states). */
  clean?: (item: string) => string;
}

export function ListField({ value, onChange, mode = "lines", single, rows = 3, clean, ...rest }: ListFieldProps) {
  const [raw, setRaw] = useState(() => joinList(value, mode));
  const rawRef = useRef(raw);
  rawRef.current = raw;

  useEffect(() => {
    if (!same(parseList(rawRef.current, mode), value)) setRaw(joinList(value, mode));
  }, [value, mode]);

  const handle = (text: string) => {
    setRaw(text);
    const items = parseList(text, mode);
    onChange(clean ? items.map(clean) : items);
  };
  const tidy = () => setRaw(joinList(clean ? parseList(raw, mode).map(clean) : parseList(raw, mode), mode));

  return single ? (
    <Input value={raw} onChange={(e) => handle(e.target.value)} onBlur={tidy} {...rest} />
  ) : (
    <Textarea rows={rows} value={raw} onChange={(e) => handle(e.target.value)} onBlur={tidy} {...rest} />
  );
}

interface NumberFieldProps {
  value: number;
  onChange: (next: number) => void;
  min?: number;
  max?: number;
  step?: number;
  /** Used when the box is left empty. */
  fallback: number;
  className?: string;
  "aria-label": string;
}

/** A number box that may be empty while the user types; it settles on blur. */
export function NumberField({ value, onChange, fallback, min, max, ...rest }: NumberFieldProps) {
  const [raw, setRaw] = useState(String(value));
  const rawRef = useRef(raw);
  rawRef.current = raw;

  useEffect(() => {
    if (rawRef.current.trim() !== "" && Number(rawRef.current) !== value) setRaw(String(value));
  }, [value]);

  const clamp = (n: number) => Math.min(max ?? Infinity, Math.max(min ?? -Infinity, Math.round(n)));
  const handle = (text: string) => {
    setRaw(text);
    const n = Number(text);
    if (text.trim() !== "" && Number.isFinite(n)) onChange(clamp(n));
  };
  const settle = () => {
    if (raw.trim() === "" || !Number.isFinite(Number(raw))) {
      onChange(fallback);
      setRaw(String(fallback));
    } else setRaw(String(clamp(Number(raw))));
  };

  return <Input type="number" min={min} max={max} value={raw} onChange={(e) => handle(e.target.value)} onBlur={settle} {...rest} />;
}
