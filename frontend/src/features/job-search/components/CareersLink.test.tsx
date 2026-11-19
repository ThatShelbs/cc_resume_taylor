import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Posting } from "../types";
import { CareersLink } from "./PostingCard";

const base = {
  id: "p1", title: "Director of Operations", company: "Initech", aggregator_only: false,
  company_careers_url: "https://www.initech.test/careers",
} as Posting;

describe("CareersLink", () => {
  it("links a careers-page posting to the company's careers page", () => {
    render(<CareersLink posting={base} />);
    expect(screen.getByRole("link", { name: /company careers page/i })).toHaveAttribute("href", "https://www.initech.test/careers");
  });

  it("sends a board lead to the company's own search for that title", () => {
    render(<CareersLink posting={{ ...base, aggregator_only: true, company_search_url: "https://www.initech.test/jobs?q=Director" }} />);
    expect(screen.getByRole("link", { name: /look for it on initech's site/i })).toHaveAttribute("href", "https://www.initech.test/jobs?q=Director");
  });

  it("shows nothing for a staffing agency posting or an unknown careers page", () => {
    const { container } = render(<CareersLink posting={{ ...base, agency: "Robert Half" }} />);
    expect(container).toBeEmptyDOMElement();
    const other = render(<CareersLink posting={{ ...base, company_careers_url: "" }} />);
    expect(other.container).toBeEmptyDOMElement();
  });
});
