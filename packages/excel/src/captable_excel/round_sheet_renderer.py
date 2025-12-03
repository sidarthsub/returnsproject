"""Round-style renderer (image-inspired) without Excel tables."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Border, Side, Alignment, PatternFill
from openpyxl.comments import Comment

from captable_domain.schemas import CapTableSnapshotCFG, WorkbookCFG


@dataclass
class HolderLine:
    holder_id: str
    shares: Decimal
    share_class_id: str
    investment: Optional[Decimal]


class RoundSheetRenderer:
    """Render one sheet per snapshot with columns per round (common, each preferred)."""

    def __init__(self, config: WorkbookCFG):
        self.config = config

        # Define styles
        self.blue_font = Font(color="0000FF")  # Blue for input values
        self.black_font = Font(color="000000")  # Black for calculated values
        self.green_font = Font(color="006400")  # Dark green for cross-sheet links
        self.bold_font = Font(bold=True)
        self.bold_blue_font = Font(bold=True, color="0000FF")

        # Border styles
        self.thin_border = Border(
            left=Side(style='thin'),
            right=Side(style='thin'),
            top=Side(style='thin'),
            bottom=Side(style='thin')
        )
        self.thick_border = Border(
            left=Side(style='medium'),
            right=Side(style='medium'),
            top=Side(style='medium'),
            bottom=Side(style='medium')
        )
        self.top_border = Border(top=Side(style='medium'))
        self.bottom_border = Border(bottom=Side(style='medium'))

        # Alignment
        self.center_align = Alignment(horizontal='center', vertical='center')
        self.right_align = Alignment(horizontal='right')

    def render(self, output_path: str) -> str:
        wb = self.build_workbook()
        wb.save(output_path)
        return output_path

    def build_workbook(self) -> Workbook:
        wb = Workbook()
        wb.remove(wb.active)

        for idx, snap_cfg in enumerate(self.config.cap_table_snapshots):
            prev_label = self.config.cap_table_snapshots[idx - 1].label if idx > 0 else None
            self._render_snapshot_sheet(wb, snap_cfg, prev_label)

        return wb

    # ------------------------------------------------------------------ #
    def _render_snapshot_sheet(self, wb: Workbook, snap_cfg: CapTableSnapshotCFG, prev_label: Optional[str] = None) -> None:
        snapshot = (
            snap_cfg.cap_table.snapshot(snap_cfg.as_of_date)
            if snap_cfg.as_of_date
            else snap_cfg.cap_table.current_snapshot()
        )

        sheet = wb.create_sheet(title=snap_cfg.label)
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.sheet_view.showGridLines = False  # Hide gridlines

        title_cell = sheet["A1"]
        title_cell.value = f"Cap Table - {snap_cfg.label}"
        title_cell.font = Font(size=14, bold=True)
        title_cell.alignment = self.center_align

        # Identify classes present in positions (so Seed snapshot doesn't show Series A columns)
        common_class_ids = sorted(
            {p.share_class_id for p in snapshot.positions if not p.is_option and snapshot.share_classes[p.share_class_id].share_type == "common"}
        )
        pref_class_ids = sorted(
            {p.share_class_id for p in snapshot.positions if not p.is_option and snapshot.share_classes[p.share_class_id].share_type == "preferred"}
        )

        # Determine which rounds are from previous snapshot (should be shown in green)
        prev_pref_class_ids = set()
        if prev_label:
            # Find previous snapshot config
            for cfg in self.config.cap_table_snapshots:
                if cfg.label == prev_label:
                    prev_snapshot = cfg.cap_table.snapshot(cfg.as_of_date) if cfg.as_of_date else cfg.cap_table.current_snapshot()
                    prev_pref_class_ids = {p.share_class_id for p in prev_snapshot.positions if not p.is_option and prev_snapshot.share_classes[p.share_class_id].share_type == "preferred"}
                    break

        # Get option pool creation events per round
        option_pool_by_round: Dict[str, Decimal] = {}
        for event in snap_cfg.cap_table.events:
            if hasattr(event, 'shares_authorized') and hasattr(event, 'event_date'):
                # Find which round this option pool expansion belongs to
                event_date = event.event_date
                # Associate with the preferred round that happened around the same time
                for pref_id in pref_class_ids:
                    # Find events for this preferred class
                    pref_events = [e for e in snap_cfg.cap_table.events
                                 if hasattr(e, 'share_class_id') and e.share_class_id == pref_id]
                    if pref_events:
                        # If option pool event is within 60 days of first pref event, associate it
                        first_pref_date = min(e.event_date for e in pref_events)
                        if abs((event_date - first_pref_date).days) <= 60:
                            option_pool_by_round[pref_id] = option_pool_by_round.get(pref_id, Decimal("0")) + event.shares_authorized

        option_pool = snapshot.option_pool_available

        # Build holder lines
        common_lines: List[HolderLine] = []
        pref_lines: List[HolderLine] = []
        for pos in snapshot.positions:
            if pos.is_option:
                continue
            if pos.share_class_id in common_class_ids:
                common_lines.append(HolderLine(pos.holder_id, pos.shares, pos.share_class_id, pos.cost_basis))
            elif pos.share_class_id in pref_class_ids:
                pref_lines.append(HolderLine(pos.holder_id, pos.shares, pos.share_class_id, pos.cost_basis))

        # Header columns: Common (# shares), GAP, then each preferred class ($ invested, Preferred shares, Option Pool), GAP, Total Shares/%
        col_map: Dict[str, str] = {}
        col_idx = 2  # start column B

        # Column A header
        holder_header = sheet.cell(row=3, column=1, value="Holder")
        holder_header.font = self.bold_font
        holder_header.border = Border(bottom=Side(style='medium'))
        holder_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")

        # Common shares column
        header_cell = sheet.cell(row=3, column=col_idx, value="Common # Shares")
        header_cell.font = self.bold_font
        header_cell.border = Border(bottom=Side(style='medium'), left=Side(style='thin'))
        header_cell.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        col_map["common_shares"] = self._col_letter(col_idx)
        col_idx += 1

        # GAP after common
        col_idx += 1

        # Preferred rounds (each with $Invested, Preferred Shares, Option Pool)
        for pref_id in pref_class_ids:
            inv_header = sheet.cell(row=3, column=col_idx, value=f"{pref_id} $ Invested")
            inv_header.font = self.bold_font
            inv_header.border = Border(bottom=Side(style='medium'), left=Side(style='thin'))
            inv_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
            col_map[f"{pref_id}_invested"] = self._col_letter(col_idx)
            col_idx += 1

            sh_header = sheet.cell(row=3, column=col_idx, value=f"{pref_id} Preferred Shares")
            sh_header.font = self.bold_font
            sh_header.border = Border(bottom=Side(style='medium'))
            sh_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
            col_map[f"{pref_id}_shares"] = self._col_letter(col_idx)
            col_idx += 1

            # Option Pool column for this round
            opt_header = sheet.cell(row=3, column=col_idx, value=f"{pref_id} Option Pool")
            opt_header.font = self.bold_font
            opt_header.border = Border(bottom=Side(style='medium'))
            opt_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
            col_map[f"{pref_id}_option_pool"] = self._col_letter(col_idx)
            col_idx += 1

            # GAP after each preferred round
            col_idx += 1

        # GAP before summary columns (already added after each round)

        # Total Shares (FD) - consolidated column
        tot_sh_header = sheet.cell(row=3, column=col_idx, value="Total Shares (FD)")
        tot_sh_header.font = self.bold_font
        tot_sh_header.border = Border(bottom=Side(style='medium'), left=Side(style='thin'))
        tot_sh_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        col_map["total_shares"] = self._col_letter(col_idx)
        col_idx += 1

        # % FD
        pct_fd_header = sheet.cell(row=3, column=col_idx, value="% FD")
        pct_fd_header.font = self.bold_font
        pct_fd_header.border = Border(bottom=Side(style='medium'))
        pct_fd_header.fill = PatternFill(start_color="E0E0E0", end_color="E0E0E0", fill_type="solid")
        col_map["pct_fd"] = self._col_letter(col_idx)

        # Common holder lines
        row = 4
        for line in common_lines:
            holder_cell = sheet[f"A{row}"]
            holder_cell.value = line.holder_id

            shares_cell = sheet[f"{col_map['common_shares']}{row}"]
            if prev_label:
                # Value with comment indicating it's from previous round
                # Use actual value but color green to show it's linked conceptually
                shares_cell.value = float(line.shares)
                shares_cell.font = self.green_font  # Indicates value from previous round
                shares_cell.comment = Comment(f"Value from {prev_label}", "System")
            else:
                # Hardcoded value for first snapshot
                shares_cell.value = float(line.shares)
                shares_cell.font = self.blue_font  # Hardcoded value
            shares_cell.number_format = '#,##0'
            row += 1

        # EMPTY ROW after common holders
        row += 1

        # Option Pool section (2 rows: Allocated Options and ESOP Available)
        allocated_row = row
        available_row = row + 1

        # Get total option pool metrics
        option_pool_authorized = snapshot.option_pool_authorized  # Total authorized
        option_pool_available = snapshot.option_pool_available  # Available for grant
        # Allocated = Authorized - Available
        option_pool_allocated = option_pool_authorized - option_pool_available if option_pool_authorized and option_pool_available else Decimal("0")

        # Allocated Options row
        alloc_label = sheet[f"A{allocated_row}"]
        alloc_label.value = "Allocated Options"
        alloc_label.font = Font(italic=True)

        # ESOP Available row
        avail_label = sheet[f"A{available_row}"]
        avail_label.value = "ESOP Available"
        avail_label.font = Font(italic=True)

        # Populate option pool values per round
        # Show option pool expansion in each round's column
        for pref_id in pref_class_ids:
            opt_col = col_map[f"{pref_id}_option_pool"]
            is_prev_round = pref_id in prev_pref_class_ids

            # Get option pool expansion for this specific round
            round_option_pool = option_pool_by_round.get(pref_id, Decimal("0"))

            if round_option_pool and round_option_pool > 0:
                # For rounds with option pool expansion, show in ESOP Available
                avail_cell = sheet[f"{opt_col}{available_row}"]
                avail_cell.value = float(round_option_pool)
                if is_prev_round:
                    avail_cell.font = self.green_font
                    avail_cell.comment = Comment(f"Value from {prev_label}", "System")
                else:
                    avail_cell.font = self.blue_font
                avail_cell.number_format = '#,##0'

        row = available_row + 1

        # EMPTY ROW after option pool
        row += 1

        # Preferred section header - add separator border
        pref_header_row = row
        pref_header_cell = sheet[f"A{pref_header_row}"]
        pref_header_cell.value = "Preferred Rounds"
        pref_header_cell.font = Font(italic=True, bold=True)
        pref_header_cell.border = Border(top=Side(style='thin'))
        row += 1

        # Preferred holder lines
        pref_start_row = row

        for pref_id in pref_class_ids:
            # Get lines for this preferred class
            class_lines = [line for line in pref_lines if line.share_class_id == pref_id]

            if not class_lines:
                continue

            # Determine if this round is from previous snapshot
            is_prev_round = pref_id in prev_pref_class_ids

            # Add investor rows for this round
            for line in class_lines:
                holder_cell = sheet[f"A{row}"]
                holder_cell.value = line.holder_id

                invest_col = col_map[f"{pref_id}_invested"]
                shares_col = col_map[f"{pref_id}_shares"]

                # Investment: use cost_basis if present
                invest_cell = sheet[f"{invest_col}{row}"]
                invest_cell.value = float(line.investment) if line.investment is not None else None
                if is_prev_round:
                    invest_cell.font = self.green_font  # From previous round
                    invest_cell.comment = Comment(f"Value from {prev_label}", "System")
                else:
                    invest_cell.font = self.blue_font  # Hardcoded value
                invest_cell.number_format = '$#,##0'

                # Shares will be formula (black font applied later)
                shares_cell = sheet[f"{shares_col}{row}"]
                shares_cell.value = None  # formula applied after PPS rows are defined
                shares_cell.number_format = '#,##0'
                row += 1

        # EMPTY ROW after preferred holders
        row += 1

        totals_row = row
        totals_label = sheet[f"A{totals_row}"]
        totals_label.value = "Totals"
        totals_label.font = self.bold_font
        totals_label.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))

        # Totals formulas
        common_sum_range = f"{col_map['common_shares']}4:{col_map['common_shares']}{pref_header_row - 1}"
        common_total = sheet[f"{col_map['common_shares']}{totals_row}"]
        common_total.value = f"=SUM({common_sum_range})"
        common_total.font = self.black_font  # Calculated
        common_total.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
        common_total.number_format = '#,##0'

        for pref_id in pref_class_ids:
            shares_col = col_map[f"{pref_id}_shares"]
            invest_col = col_map[f"{pref_id}_invested"]
            opt_col = col_map[f"{pref_id}_option_pool"]
            sum_range_sh = f"{shares_col}{pref_start_row}:{shares_col}{row-1}"
            sum_range_inv = f"{invest_col}{pref_start_row}:{invest_col}{row-1}"

            shares_total = sheet[f"{shares_col}{totals_row}"]
            shares_total.value = f"=SUM({sum_range_sh})"
            shares_total.font = self.black_font  # Calculated
            shares_total.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
            shares_total.number_format = '#,##0'

            invest_total = sheet[f"{invest_col}{totals_row}"]
            invest_total.value = f"=SUM({sum_range_inv})"
            invest_total.font = self.black_font  # Calculated
            invest_total.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
            invest_total.number_format = '$#,##0'

            # Option pool total for this round (sum of allocated + available)
            opt_total = sheet[f"{opt_col}{totals_row}"]
            opt_total.value = f"=IFERROR({opt_col}{allocated_row}+{opt_col}{available_row},0)"
            opt_total.font = self.black_font  # Calculated
            opt_total.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
            opt_total.number_format = '#,##0'

        # Total Shares (FD) = sum of common + preferred + all option pools
        components = [f"{col_map['common_shares']}{totals_row}"] + [
            f"{col_map[f'{pid}_shares']}{totals_row}" for pid in pref_class_ids
        ] + [f"{col_map[f'{pid}_option_pool']}{totals_row}" for pid in pref_class_ids]

        total_shares_totals = sheet[f"{col_map['total_shares']}{totals_row}"]
        total_shares_totals.value = f"={'+'.join(components)}"
        total_shares_totals.font = self.black_font  # Calculated
        total_shares_totals.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
        total_shares_totals.number_format = '#,##0'

        # Add % FD total (100%) in totals row
        pct_fd_total = sheet[f"{col_map['pct_fd']}{totals_row}"]
        pct_fd_total.value = 1.0
        pct_fd_total.font = self.black_font  # Should equal 100%
        pct_fd_total.border = Border(top=Side(style='medium'), bottom=Side(style='medium'))
        pct_fd_total.number_format = '0.0%'

        # Price per share / pre-money / post-money rows (per class)
        # Add separate row for starting shares to avoid confusion
        starting_shares_row = totals_row + 1
        pre_row = totals_row + 2
        price_row = totals_row + 3
        post_row = totals_row + 4

        start_label = sheet[f"A{starting_shares_row}"]
        start_label.value = "Starting Shares (pre-round)"
        start_label.font = Font(italic=True)
        start_label.border = Border(top=Side(style='thin'))

        pre_label = sheet[f"A{pre_row}"]
        pre_label.value = "Pre-Money Valuation"
        pre_label.font = self.bold_font
        pre_label.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        pre_label.border = Border(left=Side(style='thin'), top=Side(style='thin'))

        price_label = sheet[f"A{price_row}"]
        price_label.value = "Price per Share"
        price_label.font = self.bold_font
        price_label.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        price_label.border = Border(left=Side(style='thin'))

        post_label = sheet[f"A{post_row}"]
        post_label.value = "Post-Money Valuation"
        post_label.font = self.bold_font
        post_label.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
        post_label.border = Border(left=Side(style='thin'), bottom=Side(style='thin'))

        pps_cells: Dict[str, str] = {}
        # Build starting shares per class (cumulative before that class)
        start_shares_cells: Dict[str, str] = {}
        common_total_cell = f"{col_map['common_shares']}{totals_row}"
        for idx, pref_id in enumerate(pref_class_ids):
            prev_pref_totals = [
                f"{col_map[f'{pid}_shares']}{totals_row}" for pid in pref_class_ids[:idx]
            ]
            prev_option_totals = [
                f"{col_map[f'{pid}_option_pool']}{totals_row}" for pid in pref_class_ids[:idx]
            ]
            start_formula_parts = [common_total_cell] + prev_pref_totals + prev_option_totals
            # Put starting shares in the STARTING SHARES row, in the shares column
            start_cell_ref = f"{col_map[f'{pref_id}_shares']}{starting_shares_row}"
            start_cell = sheet[start_cell_ref]
            start_cell.value = f"={'+'.join(start_formula_parts)}"
            start_cell.font = self.black_font  # Calculated
            start_cell.number_format = '#,##0'
            start_shares_cells[pref_id] = start_cell_ref

        # Calculate pre-money values from actual data (reverse-engineer from investments and shares)
        pref_pre_money: Dict[str, Optional[Decimal]] = {}
        for pref_id in pref_class_ids:
            # Get total investment and shares for this class
            class_lines = [line for line in pref_lines if line.share_class_id == pref_id]
            if not class_lines:
                pref_pre_money[pref_id] = None
                continue

            total_investment = sum(line.investment for line in class_lines if line.investment)
            total_shares = sum(line.shares for line in class_lines)

            if total_investment and total_shares and total_investment > 0 and total_shares > 0:
                # PPS = total investment / total shares
                pps = total_investment / total_shares

                # Pre-money = PPS * (shares before this round)
                # Calculate shares before this round
                idx = pref_class_ids.index(pref_id)
                shares_before = (
                    sum(line.shares for line in common_lines) +
                    sum(option_pool_by_round.get(pid, Decimal("0")) for pid in pref_class_ids[:idx]) +
                    sum(sum(l.shares for l in pref_lines if l.share_class_id == pid)
                        for pid in pref_class_ids[:idx])
                )

                pre_money = pps * shares_before
                pref_pre_money[pref_id] = pre_money
            else:
                pref_pre_money[pref_id] = None

        for idx, pref_id in enumerate(pref_class_ids):
            invest_col = col_map[f"{pref_id}_invested"]
            shares_col = col_map[f"{pref_id}_shares"]
            start_cell = start_shares_cells[pref_id]

            pre_money_cell_ref = f"{invest_col}{pre_row}"
            pps_cell_ref = f"{invest_col}{price_row}"
            post_money_cell_ref = f"{invest_col}{post_row}"

            pps_cells[pref_id] = pps_cell_ref

            # Determine if this is the first or last preferred round for border styling
            is_first_pref = (idx == 0)
            is_last_pref = (idx == len(pref_class_ids) - 1)

            # Determine if this round is from previous snapshot
            is_prev_round = pref_id in prev_pref_class_ids

            # Starting shares cell
            start_cell_obj = sheet[start_cell]
            start_cell_obj.border = Border(
                left=Side(style='thin') if is_first_pref else None,
                right=Side(style='thin') if is_last_pref else None,
                top=Side(style='thin')
            )

            # Pre-money calculated from actual data (user can edit)
            pre_money_cell = sheet[pre_money_cell_ref]
            if pref_pre_money.get(pref_id) is not None:
                pre_money_cell.value = float(pref_pre_money[pref_id])
            else:
                pre_money_cell.value = None

            if is_prev_round:
                pre_money_cell.font = self.green_font  # From previous round
                pre_money_cell.comment = Comment(f"Value from {prev_label}", "System")
            else:
                pre_money_cell.font = self.blue_font  # User editable input

            pre_money_cell.number_format = '$#,##0'
            pre_money_cell.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
            pre_money_cell.border = Border(
                left=Side(style='thin') if is_first_pref else None,
                right=Side(style='thin') if is_last_pref else None,
                top=Side(style='thin')
            )

            # PPS = pre-money / starting shares
            pps_cell = sheet[pps_cell_ref]
            pps_cell.value = f"=IFERROR({pre_money_cell_ref}/{start_cell},\"\")"
            pps_cell.font = self.black_font  # Always calculated from formula
            pps_cell.number_format = '$0.00'
            pps_cell.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
            pps_cell.border = Border(
                left=Side(style='thin') if is_first_pref else None,
                right=Side(style='thin') if is_last_pref else None
            )

            # Post-money = pre-money + total invested for this class
            post_money_cell = sheet[post_money_cell_ref]
            post_money_cell.value = f"=IFERROR({pre_money_cell_ref}+{invest_col}{totals_row},\"\")"
            post_money_cell.font = self.black_font  # Always calculated from formula
            post_money_cell.number_format = '$#,##0'
            post_money_cell.fill = PatternFill(start_color="F0F0F0", end_color="F0F0F0", fill_type="solid")
            post_money_cell.border = Border(
                left=Side(style='thin') if is_first_pref else None,
                right=Side(style='thin') if is_last_pref else None,
                bottom=Side(style='thin')
            )

            # Apply per-holder shares = investment / PPS
            # Only add formula if the investor actually has an investment in this round
            for r in range(pref_start_row, row):
                invest_value = sheet[f"{invest_col}{r}"].value
                # Only add shares formula if there's an investment amount
                if invest_value is not None and invest_value != "":
                    shares_formula_cell = sheet[f"{shares_col}{r}"]
                    shares_formula_cell.value = f"=IFERROR({invest_col}{r}/{pps_cell_ref},0)"
                    if is_prev_round:
                        shares_formula_cell.font = self.green_font  # From previous round (still formula but green)
                    else:
                        shares_formula_cell.font = self.black_font  # Calculated from investment/PPS

        # Total Shares and % FD per holder rows
        share_columns = [col_map["common_shares"]] + [col_map[f"{pid}_shares"] for pid in pref_class_ids] + [col_map[f"{pid}_option_pool"] for pid in pref_class_ids]

        for r in range(4, row):
            # Get the holder name in column A
            cell_a_value = sheet.cell(row=r, column=1).value

            # Skip empty rows, header rows, and section separators
            if not cell_a_value:
                continue
            if r == pref_header_row:
                continue
            if cell_a_value == "Preferred Rounds":
                continue

            # Handle option pool rows specially
            if cell_a_value in ["Allocated Options", "ESOP Available"]:
                # Still calculate Total Shares for option pool rows
                share_sums = "+".join(f"{col}{r}" for col in share_columns)
                total_shares_cell = sheet[f"{col_map['total_shares']}{r}"]
                total_shares_cell.value = f"=IFERROR({share_sums},\"\")"  # Blank if 0
                total_shares_cell.font = self.black_font  # Calculated
                total_shares_cell.number_format = '#,##0'

                # % FD for option pool rows
                pct_fd_cell = sheet[f"{col_map['pct_fd']}{r}"]
                pct_fd_cell.value = f"=IFERROR({col_map['total_shares']}{r}/{col_map['total_shares']}{totals_row},\"\")"  # Blank if 0
                pct_fd_cell.font = self.black_font  # Calculated
                pct_fd_cell.number_format = '0.0%'
                continue

            # Total Shares = sum of all share columns for this holder
            share_sums = "+".join(f"{col}{r}" for col in share_columns)
            total_shares_cell = sheet[f"{col_map['total_shares']}{r}"]
            total_shares_cell.value = f"=IFERROR({share_sums},\"\")"  # Blank if 0
            total_shares_cell.font = self.black_font  # Calculated
            total_shares_cell.number_format = '#,##0'

            # % FD = Total Shares / Total Shares in totals row
            pct_fd_cell = sheet[f"{col_map['pct_fd']}{r}"]
            pct_fd_cell.value = f"=IFERROR({col_map['total_shares']}{r}/{col_map['total_shares']}{totals_row},\"\")"  # Blank if 0
            pct_fd_cell.font = self.black_font  # Calculated
            pct_fd_cell.number_format = '0.0%'

        # Adjust column widths for better readability
        sheet.column_dimensions['A'].width = 25  # Holder names
        sheet.column_dimensions[col_map['common_shares']].width = 15  # Common shares
        for pref_id in pref_class_ids:
            sheet.column_dimensions[col_map[f"{pref_id}_invested"]].width = 15  # $ Invested
            sheet.column_dimensions[col_map[f"{pref_id}_shares"]].width = 15  # Preferred shares
            sheet.column_dimensions[col_map[f"{pref_id}_option_pool"]].width = 15  # Option pool
        sheet.column_dimensions[col_map['total_shares']].width = 15  # Total shares (FD)
        sheet.column_dimensions[col_map['pct_fd']].width = 12  # % FD

        # Add box around entire cap table
        # Determine bounds: from row 3 (headers) to post_row (last valuation row), from column A to last column (% FD)
        first_row = 3
        last_row = post_row
        first_col = 1  # A
        last_col = self._col_to_index(col_map['pct_fd'])

        # Apply thick border to outer edges
        for c in range(first_col, last_col + 1):
            # Top border on header row
            cell = sheet.cell(row=first_row, column=c)
            cell.border = Border(
                left=cell.border.left if cell.border else None,
                right=cell.border.right if cell.border else None,
                top=Side(style='medium'),
                bottom=cell.border.bottom if cell.border else None
            )
            # Bottom border on last row
            cell = sheet.cell(row=last_row, column=c)
            cell.border = Border(
                left=cell.border.left if cell.border else None,
                right=cell.border.right if cell.border else None,
                top=cell.border.top if cell.border else None,
                bottom=Side(style='medium')
            )

        for r in range(first_row, last_row + 1):
            # Left border on column A
            cell = sheet.cell(row=r, column=first_col)
            cell.border = Border(
                left=Side(style='medium'),
                right=cell.border.right if cell.border else None,
                top=cell.border.top if cell.border else None,
                bottom=cell.border.bottom if cell.border else None
            )
            # Right border on last column
            cell = sheet.cell(row=r, column=last_col)
            cell.border = Border(
                left=cell.border.left if cell.border else None,
                right=Side(style='medium'),
                top=cell.border.top if cell.border else None,
                bottom=cell.border.bottom if cell.border else None
            )

    # ------------------------------------------------------------------ #
    @staticmethod
    def _col_to_index(col_letter: str) -> int:
        """Convert Excel column letter to 1-based index."""
        idx = 0
        for char in col_letter:
            idx = idx * 26 + (ord(char) - 64)
        return idx

    # ------------------------------------------------------------------ #
    @staticmethod
    def _col_letter(idx: int) -> str:
        """Convert 1-based column index to Excel column letter."""
        letter = ""
        while idx > 0:
            idx, rem = divmod(idx - 1, 26)
            letter = chr(65 + rem) + letter
        return letter


__all__ = ["RoundSheetRenderer"]
