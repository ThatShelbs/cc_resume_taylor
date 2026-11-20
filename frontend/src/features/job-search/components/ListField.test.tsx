import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { describe, expect, it } from "vitest";
import { ListField, NumberField, parseList } from "./ListField";

function Harness({ initial = [] as string[], mode = "lines" as "lines" | "commas", single = false }) {
  const [v, setV] = useState(initial);
  return (
    <div>
      <ListField aria-label="field" value={v} onChange={setV} mode={mode} single={single} />
      <output data-testid="out">{JSON.stringify(v)}</output>
    </div>
  );
}

describe("parseList", () => {
  it("trims, drops blanks and splits on the chosen separator", () => {
    expect(parseList(" a \n\n b ")).toEqual(["a", "b"]);
    expect(parseList("IL, WI,\nMN", "commas")).toEqual(["IL", "WI", "MN"]);
  });
});

describe("ListField", () => {
  it("keeps spaces and new lines while typing", async () => {
    const user = userEvent.setup();
    render(<Harness />);
    const box = screen.getByLabelText("field") as HTMLTextAreaElement;
    await user.type(box, "Director, Data Science{Enter}Head of Analytics ");
    expect(box.value).toBe("Director, Data Science\nHead of Analytics ");
    expect(screen.getByTestId("out").textContent).toBe(JSON.stringify(["Director, Data Science", "Head of Analytics"]));
  });

  it("lets a second comma separated item be typed", async () => {
    const user = userEvent.setup();
    render(<Harness mode="commas" single />);
    const box = screen.getByLabelText("field") as HTMLInputElement;
    await user.type(box, "IL, WI");
    expect(box.value).toBe("IL, WI");
    await user.tab();
    expect(box.value).toBe("IL, WI");
  });

  it("rewrites the box when the list changes from outside", () => {
    const { rerender } = render(<ListField aria-label="f" value={["a"]} onChange={() => {}} />);
    rerender(<ListField aria-label="f" value={["x", "y"]} onChange={() => {}} />);
    expect((screen.getByLabelText("f") as HTMLTextAreaElement).value).toBe("x\ny");
  });
});

describe("NumberField", () => {
  it("allows an empty box while typing and settles on the fallback", async () => {
    const user = userEvent.setup();
    let latest = 14;
    function H() {
      const [n, setN] = useState(14);
      latest = n;
      return <NumberField aria-label="days" value={n} onChange={setN} fallback={14} min={1} max={90} />;
    }
    render(<H />);
    const box = screen.getByLabelText("days") as HTMLInputElement;
    await user.clear(box);
    expect(box.value).toBe("");
    await user.type(box, "10");
    expect(latest).toBe(10);
    await user.clear(box);
    await user.tab();
    expect(box.value).toBe("14");
  });
});
