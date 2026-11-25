import { render, screen, fireEvent, within } from "@testing-library/react";
import { expect, it } from "vitest";
import SavedQuantumStudy from "./SavedQuantumStudy";

it("shows saved simulator comparisons and explains the size guard", () => {
  render(<SavedQuantumStudy />);
  const region = screen.getByRole("region", { name: "Saved quantum benchmark" });
  expect(within(region).getByText("Qiskit simulator")).toBeInTheDocument();
  expect(within(region).getByText("Qulacs simulator")).toBeInTheDocument();
  fireEvent.change(within(region).getByLabelText("Benchmark instance"), {target: {value: "size-control"}});
  expect(within(region).getByText(/exact\/QAOA limit/)).toBeInTheDocument();
  expect(within(region).getByText("Exact QUBO")).toBeInTheDocument();
  expect(within(region).queryByText("Qiskit simulator")).toBeNull();
});
