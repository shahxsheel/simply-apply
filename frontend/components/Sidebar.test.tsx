import type { AnchorHTMLAttributes, ReactNode } from "react";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import Sidebar from "./Sidebar";

let currentPath = "/greenhouse";

vi.mock("next/navigation", () => ({
  usePathname: () => currentPath,
}));

vi.mock("next/link", () => ({
  default: ({
    href,
    children,
    ...props
  }: AnchorHTMLAttributes<HTMLAnchorElement> & {
    href: string;
    children: ReactNode;
  }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}));

afterEach(() => cleanup());

describe("Sidebar", () => {
  it("marks the current destination in desktop and mobile navigation", () => {
    currentPath = "/greenhouse";
    const { container } = render(<Sidebar />);

    expect(
      container.querySelectorAll('a[href="/greenhouse"][aria-current="page"]'),
    ).toHaveLength(2);
    expect(
      container.querySelector('a[href="/settings"][aria-current="page"]'),
    ).not.toBeInTheDocument();
  });

  it("exposes the brand and privacy message accessibly", () => {
    currentPath = "/settings";
    render(<Sidebar />);

    expect(screen.getAllByRole("link", { name: "SimplyApply home" })).toHaveLength(2);
    expect(screen.getByText("Private by design.")).toBeInTheDocument();
  });
});
