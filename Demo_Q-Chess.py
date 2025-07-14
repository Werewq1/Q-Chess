import pygame
import asyncio
import platform
import random
from qiskit import QuantumCircuit, transpile
from qiskit_aer import Aer
import copy

# Initialize Pygame
pygame.init()

# Get screen size and set up window
WINDOW_WIDTH = pygame.display.Info().current_w
WINDOW_HEIGHT = pygame.display.Info().current_h
BOARD_SIZE_FACTOR = 0.9
SIDEBAR_WIDTH_FACTOR = 2
SQUARE_SIZE = max(50, int(min(WINDOW_WIDTH / (8 + SIDEBAR_WIDTH_FACTOR), WINDOW_HEIGHT / 8) * BOARD_SIZE_FACTOR))
BOARD_SIZE = 8 * SQUARE_SIZE
SIDEBAR_WIDTH = SQUARE_SIZE * SIDEBAR_WIDTH_FACTOR
WINDOW_SIZE = (BOARD_SIZE + SIDEBAR_WIDTH, BOARD_SIZE)

# Colors
LIGHT_SQUARE = (122, 133, 147)
DARK_SQUARE = (46, 54, 66)
YELLOW = (255, 255, 0)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (150, 150, 150)
BLUE = (0, 0, 255)
VIBRANT_RED = (255, 0, 0)
GREEN = (0, 255, 0)
ORANGE = (255, 165, 0)
LIGHT_BLUE = (135, 206, 250)  # For White split pieces
RED = (255, 0, 0)  # For Black split pieces

# Pieces (Unicode)
PIECES = {
    'wk': '♔', 'wq': '♕', 'wr': '♖', 'wb': '♗', 'wn': '♘', 'wp': '♙',
    'bk': '♚', 'bq': '♛', 'br': '♜', 'bb': '♝', 'bn': '♞', 'bp': '♟'
}

# Initial board setup
INITIAL_BOARD = [
    ['br', 'bn', 'bb', 'bq', 'bk', 'bb', 'bn', 'br'],
    ['bp', 'bp', 'bp', 'bp', 'bp', 'bp', 'bp', 'bp'],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['', '', '', '', '', '', '', ''],
    ['wp', 'wp', 'wp', 'wp', 'wp', 'wp', 'wp', 'wp'],
    ['wr', 'wn', 'wb', 'wq', 'wk', 'wb', 'wn', 'wr']
]

class SplitBranch:
    def __init__(self, pos, piece_type):
        self.pos = pos  # (row, col)
        self.piece_type = piece_type

class SplitQubit:
    def __init__(self, branch_a, branch_b, parent=None, parent_branch=None):
        self.branch_a = branch_a
        self.branch_b = branch_b
        self.parent = parent
        self.parent_branch = parent_branch
        self.children = []
        self.qubit_index = None
        self.collapsed_result = None
        if parent:
            parent.children.append(self)

class QuantumSubsystem:
    def __init__(self):
        self.split_qubits = []
        self.position_to_qubit = {}
        self.qc = QuantumCircuit()
        self.result_map = {}
        self.measured = False

    def add_split_qubit(self, branch_a, branch_b, piece_type, parent_qubit=None, parent_branch=None):
        new_qubit = SplitQubit(branch_a, branch_b, parent=parent_qubit, parent_branch=parent_branch)
        new_qubit.qubit_index = len(self.qc.qubits)
        self.qc.add_register(1)
        if parent_qubit is None:
            self.qc.h(new_qubit.qubit_index)
        else:
            ctrl = parent_qubit.qubit_index
            tgt = new_qubit.qubit_index
            if parent_branch == 'a':
                self.qc.x(ctrl)
                self.qc.ch(ctrl, tgt)
                self.qc.x(ctrl)
            else:
                self.qc.ch(ctrl, tgt)
        self.split_qubits.append(new_qubit)
        self.position_to_qubit[branch_a.pos] = (new_qubit, 'a')
        self.position_to_qubit[branch_b.pos] = (new_qubit, 'b')
        return new_qubit

    def collapse(self):
        if self.measured:
            return self.result_map
        num_qubits = len(self.split_qubits)
        qc = QuantumCircuit(num_qubits, num_qubits)
        qc.compose(self.qc, inplace=True)
        qc.measure(range(num_qubits), range(num_qubits))
        backend = Aer.get_backend('qasm_simulator')
        tqc = transpile(qc, backend)
        job = backend.run(tqc, shots=1)
        result = job.result()
        measured_str = list(result.get_counts().keys())[0]
        for qubit in self.split_qubits:
            bit = measured_str[::-1][qubit.qubit_index]
            qubit.collapsed_result = 'a' if bit == '0' else 'b'
            self.result_map[qubit] = qubit.collapsed_result
        self.measured = True
        return self.result_map

    def apply_to_board(self, board, target_qubit=None):
        if not self.measured:
            self.collapse()
        qubits_to_process = [target_qubit] if target_qubit else self.split_qubits
        for qubit in qubits_to_process:
            board[qubit.branch_a.pos[0]][qubit.branch_a.pos[1]] = ''
            board[qubit.branch_b.pos[0]][qubit.branch_b.pos[1]] = ''
            real = qubit.branch_a if qubit.collapsed_result == 'a' else qubit.branch_b
            board[real.pos[0]][real.pos[1]] = real.piece_type

class QuantumSplitManager:
    def __init__(self):
        self.subsystems = []
        self.global_position_map = {}

    def create_split_qubit(self, from_pos, to_pos, piece_type):
        parent_info = self.global_position_map.get(from_pos)
        if parent_info:
            subsystem, parent_qubit, parent_branch = parent_info
        else:
            subsystem = QuantumSubsystem()
            self.subsystems.append(subsystem)
            parent_qubit = None
            parent_branch = None
        branch_a = SplitBranch(from_pos, piece_type)
        branch_b = SplitBranch(to_pos, piece_type)
        new_qubit = subsystem.add_split_qubit(branch_a, branch_b, piece_type, parent_qubit, parent_branch)
        self.global_position_map[branch_a.pos] = (subsystem, new_qubit, 'a')
        self.global_position_map[branch_b.pos] = (subsystem, new_qubit, 'b')
        return new_qubit

    def is_split_piece(self, pos):
        return pos in self.global_position_map

    def get_qubit_for_position(self, pos):
        return self.global_position_map.get(pos)

    def collapse_qubit(self, qubit):
        for subsystem in self.subsystems:
            if qubit in subsystem.split_qubits:
                subsystem.collapse()
                return

    def collapse_all(self):
        for subsystem in self.subsystems:
            subsystem.collapse()

    def apply_collapse_to_board(self, board, target_qubit=None):
        positions_to_remove = []
        for subsystem in self.subsystems:
            if subsystem.measured:
                subsystem.apply_to_board(board, target_qubit)
                for pos, (sub, qubit, branch) in list(self.global_position_map.items()):
                    if sub == subsystem and (target_qubit is None or qubit == target_qubit):
                        positions_to_remove.append(pos)
        for pos in positions_to_remove:
            del self.global_position_map[pos]

    def get_split_positions(self):
        """Returns a list of split piece positions grouped by subsystem."""
        split_groups = []
        processed_qubits = set()
        for subsystem in self.subsystems:
            if not subsystem.measured:
                group = []
                for qubit in subsystem.split_qubits:
                    if qubit not in processed_qubits:
                        group.append((qubit.branch_a.pos, qubit.branch_a.piece_type))
                        group.append((qubit.branch_b.pos, qubit.branch_b.piece_type))
                        processed_qubits.add(qubit)
                if group:
                    split_groups.append(group)
        return split_groups

class ChessGame:
    def __init__(self):
        self.screen = pygame.display.set_mode(WINDOW_SIZE)
        pygame.display.set_caption("Chess Game")
        font_size = int(SQUARE_SIZE // 2)
        self.font = pygame.font.SysFont(['Segoe UI Symbol', 'Arial Unicode MS', 'Arial', 'sans-serif'], font_size)
        self.board = [row[:] for row in INITIAL_BOARD]
        self.turn = 'w'
        self.selected = None
        self.valid_moves = []
        self.captured = {'w': [], 'b': []}
        self.en_passant = None
        self.castling = {'w': {'king': False, 'queen': False, 'king_nm': True, 'queen_nm': True}, 'b': {'king': False, 'queen': False, 'king_nm': True, 'queen_nm': True}}
        self.history = []
        self.running = True
        self.promotion_pending = False
        self.promotion_pos = None
        self.promotion_options = ['q', 'r', 'b', 'n']
        self.check_cache = {'w': None, 'b': None}
        self.game_over = False
        self.edit_mode = False
        self.selected_piece_to_place = None
        self.piece_options = ['wp', 'wn', 'wb', 'wr', 'wq', 'wk', 'bp', 'bn', 'bb', 'br', 'bq', 'bk', 'delete']
        self.draw_by_stalemate = False
        self.split_mode = False
        self.split_manager = QuantumSplitManager()

    def draw_board(self):
        if self.game_over:
            if self.draw_by_stalemate:
                self.draw_stalemate_screen()
            else:
                self.draw_checkmate_screen()
            return
        flip = self.turn == 'b'
        for row in range(8):
            for col in range(8):
                display_row = 7 - row if flip else row
                display_col = 7 - col if flip else col
                color = LIGHT_SQUARE if (row + col) % 2 == 0 else DARK_SQUARE
                pygame.draw.rect(self.screen, color, (display_col * SQUARE_SIZE, display_row * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE))
                if not self.edit_mode and (display_row, display_col) in [(7 - r if flip else r, 7 - c if flip else c) for r, c in self.valid_moves]:
                    pygame.draw.rect(self.screen, YELLOW, (display_col * SQUARE_SIZE, display_row * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE), 3)
                piece = self.board[row][col]
                if piece in ['wk', 'bk']:
                    color = 'w' if piece == 'wk' else 'b'
                    if self.is_in_check(color, simple=False) and self.is_square_attacked(row, col, color, simple=False):
                        pygame.draw.rect(self.screen, VIBRANT_RED, (display_col * SQUARE_SIZE, display_row * SQUARE_SIZE, SQUARE_SIZE, SQUARE_SIZE), 3)
                        print(f"King at (row, col)=({row}, {col}) highlighted in red because it's in check")
                if piece:
                    piece_color = WHITE if piece[0] == 'w' else BLACK
                    if self.split_manager.is_split_piece((row, col)):
                        piece_color = LIGHT_BLUE if piece[0] == 'w' else RED
                    text = self.font.render(PIECES[piece], True, piece_color)
                    text_rect = text.get_rect(center=(display_col * SQUARE_SIZE + SQUARE_SIZE // 2, display_row * SQUARE_SIZE + SQUARE_SIZE // 2))
                    self.screen.blit(text, text_rect)

    def draw_sidebar(self):
        if self.game_over:
            return
        pygame.draw.rect(self.screen, GRAY, (BOARD_SIZE, 0, SIDEBAR_WIDTH, BOARD_SIZE))
        edit_button_rect = pygame.Rect(BOARD_SIZE + SQUARE_SIZE // 4, SQUARE_SIZE // 4, SQUARE_SIZE * 1.5, SQUARE_SIZE // 2)
        pygame.draw.rect(self.screen, ORANGE if self.edit_mode else BLUE, edit_button_rect)
        edit_text = self.font.render("Edit", True, WHITE)
        text_rect = edit_text.get_rect(center=edit_button_rect.center)
        self.screen.blit(edit_text, text_rect)

        split_button_rect = pygame.Rect(BOARD_SIZE + SQUARE_SIZE // 4, SQUARE_SIZE, SQUARE_SIZE * 1.5, SQUARE_SIZE // 2)
        pygame.draw.rect(self.screen, ORANGE if self.split_mode else BLUE, split_button_rect)
        split_text = self.font.render("Split", True, WHITE)
        text_rect = split_text.get_rect(center=split_button_rect.center)
        self.screen.blit(split_text, text_rect)

        if self.edit_mode:
            for i, piece in enumerate(self.piece_options):
                piece_y = SQUARE_SIZE * 2 + i * SQUARE_SIZE // 2
                button_rect = pygame.Rect(BOARD_SIZE + SQUARE_SIZE // 4, piece_y, SQUARE_SIZE * 1.5, SQUARE_SIZE // 2)
                color = YELLOW if self.selected_piece_to_place == piece else BLUE
                pygame.draw.rect(self.screen, color, button_rect)
                if piece == 'delete':
                    text = self.font.render("Delete", True, BLACK)
                else:
                    piece_color = WHITE if piece[0] == 'w' else BLACK
                    text = self.font.render(PIECES[piece], True, piece_color)
                text_rect = text.get_rect(center=button_rect.center)
                self.screen.blit(text, text_rect)
        else:
            offset_y = SQUARE_SIZE * 2
            for i, piece in enumerate(self.captured['w']):
                piece_color = WHITE if piece[0] == 'w' else BLACK
                text = self.font.render(PIECES[piece], True, piece_color)
                text_rect = text.get_rect(center=(BOARD_SIZE + SQUARE_SIZE // 2, offset_y + i * SQUARE_SIZE // 2 + SQUARE_SIZE // 2))
                self.screen.blit(text, text_rect)
            for i, piece in enumerate(self.captured['b']):
                piece_color = WHITE if piece[0] == 'w' else BLACK
                text = self.font.render(PIECES[piece], True, piece_color)
                text_rect = text.get_rect(center=(BOARD_SIZE + SQUARE_SIZE + SQUARE_SIZE // 2, offset_y + i * SQUARE_SIZE // 2 + SQUARE_SIZE // 2))
                self.screen.blit(text, text_rect)
            if self.promotion_pending:
                promo_y = BOARD_SIZE - 4 * SQUARE_SIZE // 2
                for i, option in enumerate(self.promotion_options):
                    piece = f"{self.turn}{option}"
                    button_rect = pygame.Rect(
                        BOARD_SIZE + SQUARE_SIZE // 4,
                        promo_y + i * SQUARE_SIZE // 2,
                        SQUARE_SIZE * 1.5,
                        SQUARE_SIZE // 2
                    )
                    pygame.draw.rect(self.screen, BLUE, button_rect)
                    text = self.font.render(PIECES[piece], True, WHITE if self.turn == 'w' else BLACK)
                    text_rect = text.get_rect(center=button_rect.center)
                    self.screen.blit(text, text_rect)

    def draw_checkmate_screen(self):
        self.screen.fill(BLACK)
        winner = 'White' if self.turn == 'b' else 'Black'
        game_over_text = self.font.render(f"Game Over - {winner} Wins by Checkmate!", True, GREEN)
        text_rect = game_over_text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
        self.screen.blit(game_over_text, text_rect)
        pygame.display.flip()

    def draw_stalemate_screen(self):
        self.screen.fill(BLACK)
        stalemate_text = self.font.render("Game Over - Draw by Stalemate!", True, GREEN)
        text_rect = stalemate_text.get_rect(center=(WINDOW_SIZE[0] // 2, WINDOW_SIZE[1] // 2))
        self.screen.blit(stalemate_text, text_rect)
        pygame.display.flip()

    def get_square(self, pos):
        x, y = pos
        if x < BOARD_SIZE and y < BOARD_SIZE and not self.game_over:
            col = x // SQUARE_SIZE
            row = y // SQUARE_SIZE
            flip = self.turn == 'b'
            if flip:
                col = 7 - col
                row = 7 - row
            print(f"Clicked at pos {pos}, mapped to square (row, col): ({row}, {col})")
            return col, row
        return None

    def get_edit_choice(self, pos):
        x, y = pos
        if BOARD_SIZE + SQUARE_SIZE // 4 <= x <= BOARD_SIZE + SQUARE_SIZE * 1.75:
            edit_button_top = SQUARE_SIZE // 4
            edit_button_bottom = edit_button_top + SQUARE_SIZE // 2
            if edit_button_top <= y <= edit_button_bottom:
                return 'toggle_edit'
            if self.edit_mode:
                for i, piece in enumerate(self.piece_options):
                    piece_top = SQUARE_SIZE * 2 + i * SQUARE_SIZE // 2
                    piece_bottom = piece_top + SQUARE_SIZE // 2
                    if piece_top <= y <= piece_bottom:
                        print(f"Selected piece to place: {piece}")
                        return piece
        return None

    def get_promotion_choice(self, pos):
        if not self.promotion_pending or self.game_over:
            return None
        x, y = pos
        if BOARD_SIZE + SQUARE_SIZE // 4 <= x <= BOARD_SIZE + SQUARE_SIZE * 1.75:
            promo_y = BOARD_SIZE - 4 * SQUARE_SIZE // 2
            for i, option in enumerate(self.promotion_options):
                button_top = promo_y + i * SQUARE_SIZE // 2
                button_bottom = button_top + SQUARE_SIZE // 2
                if button_top <= y <= button_bottom:
                    print(f"Selected promotion piece: {option}")
                    return option
        return None

    def get_valid_moves(self, col, row, simple=False):
        if self.game_over or self.edit_mode:
            return []
        piece = self.board[row][col]
        if not simple and (not piece or piece[0] != self.turn):
            print(f"No valid piece at (row, col)=({row}, {col}) or not your turn. Piece: {piece}, Turn: {self.turn}")
            return []
        if not piece:
            print(f"No piece at (row, col)=({row}, {col})")
            return []
        moves = []
        if piece[1] == 'p':
            moves = self.get_pawn_moves(row, col)
        elif piece[1] == 'n':
            moves = self.get_knight_moves(row, col)
        elif piece[1] == 'b':
            moves = self.get_bishop_moves(row, col)
        elif piece[1] == 'r':
            moves = self.get_rook_moves(row, col)
        elif piece[1] == 'q':
            moves = self.get_queen_moves(row, col)
        elif piece[1] == 'k':
            moves = self.get_king_moves(row, col, simple=simple)
        if simple:
            print(f"Simple moves for {piece} at (row, col)=({row}, {col}): {moves}")
            return moves
        legal_moves = [(r, c) for r, c in moves if self.is_legal_move(row, col, r, c)]
        print(f"Legal moves for {piece} at (row, col)=({row}, {col}): {legal_moves}")
        return legal_moves

    def get_pawn_moves(self, row, col):
        moves = []
        direction = -1 if self.turn == 'w' else 1
        start_row = 6 if self.turn == 'w' else 1
        if 0 <= row + direction < 8:
            target_pos = (row + direction, col)
            target_piece = self.board[row + direction][col]
            if not target_piece:
                moves.append(target_pos)
                if row == start_row and 0 <= row + 2 * direction < 8:
                    target_pos = (row + 2 * direction, col)
                    target_piece = self.board[row + 2 * direction][col]
                    if not target_piece:
                        moves.append(target_pos)
        for dc in [-1, 1]:
            nc = col + dc
            if 0 <= row + direction < 8 and 0 <= nc < 8:
                target_pos = (row + direction, nc)
                target_piece = self.board[row + direction][nc]
                if target_piece and target_piece[0] != self.turn:
                    moves.append(target_pos)
                if target_pos == self.en_passant:
                    moves.append(target_pos)
        print(f"Pawn moves from (row, col)=({row}, {col}): {moves}")
        return moves

    def get_knight_moves(self, row, col):
        moves = []
        for dr, dc in [(-2, -1), (-2, 1), (-1, -2), (-1, 2), (1, -2), (1, 2), (2, -1), (2, 1)]:
            r, c = row + dr, col + dc
            if 0 <= r < 8 and 0 <= c < 8:
                target_pos = (r, c)
                target_piece = self.board[r][c]
                if not target_piece or target_piece[0] != self.turn:
                    moves.append(target_pos)
        print(f"Knight moves from (row, col)=({row}, {col}): {moves}")
        return moves

    def get_bishop_moves(self, row, col):
        moves = []
        for dr, dc in [(-1, -1), (-1, 1), (1, -1), (1, 1)]:
            r, c = row, col
            while True:
                r, c = r + dr, c + dc
                if 0 <= r < 8 and 0 <= c < 8:
                    target_pos = (r, c)
                    target_piece = self.board[r][c]
                    if not target_piece:
                        moves.append(target_pos)
                    elif target_piece[0] != self.turn:
                        moves.append(target_pos)
                        break
                    else:
                        break
                else:
                    break
        print(f"Bishop moves from (row, col)=({row}, {col}): {moves}")
        return moves

    def get_rook_moves(self, row, col):
        moves = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            r, c = row, col
            while True:
                r, c = r + dr, c + dc
                if 0 <= r < 8 and 0 <= c < 8:
                    target_pos = (r, c)
                    target_piece = self.board[r][c]
                    if not target_piece:
                        moves.append(target_pos)
                    elif target_piece[0] != self.turn:
                        moves.append(target_pos)
                        break
                    else:
                        break
                else:
                    break
        print(f"Rook moves from (row, col)=({row}, {col}): {moves}")
        return moves

    def get_queen_moves(self, row, col):
        rook_moves = self.get_rook_moves(row, col)
        bishop_moves = self.get_bishop_moves(row, col)
        moves = rook_moves + bishop_moves
        print(f"Queen moves from (row, col)=({row}, {col}): Rook moves={rook_moves}, Bishop moves={bishop_moves}, Total={moves}")
        return moves

    def get_king_moves(self, row, col, simple=False):
        moves = []
        for dr in [-1, 0, 1]:
            for dc in [-1, 0, 1]:
                if dr == 0 and dc == 0:
                    continue
                r, c = row + dr, col + dc
                if 0 <= r < 8 and 0 <= c < 8:
                    target_pos = (r, c)
                    target_piece = self.board[r][c]
                    if not target_piece or target_piece[0] != self.turn:
                        moves.append(target_pos)
        if not simple and (self.castling[self.turn]['king_nm'] or self.castling[self.turn]['queen_nm']):
            if self.can_castle(row, col):
                if self.castling[self.turn]['king']:
                    moves.append((row, col + 2))
                if self.castling[self.turn]['queen']:
                    moves.append((row, col - 2))
        print(f"King moves from (row, col)=({row}, {col}): {moves}")
        return moves

    def can_castle(self, row, col):
        if self.board[row][col][1] != 'k' or not self.castling[self.turn]['king_nm'] and not self.castling[self.turn]['queen_nm']:
            return False
        if self.is_in_check(self.turn, simple=True):
            return False
        c = 0
        if self.castling[self.turn]['king_nm']:
            if not self.board[row][col + 1] and not self.board[row][col + 2]:
                if not self.is_square_attacked(row, col + 1, self.turn, simple=True) and not self.is_square_attacked(row, col + 2, self.turn, simple=True):
                    self.castling[self.turn]['king'] = True
                    c = 1
        if self.castling[self.turn]['queen_nm']:
            if not self.board[row][col - 1] and not self.board[row][col - 2] and not self.board[row][col - 3]:
                if not self.is_square_attacked(row, col - 1, self.turn, simple=True) and not self.is_square_attacked(row, col - 2, self.turn, simple=True):
                    self.castling[self.turn]['queen'] = True
                    c = 1
        if c != 0:
            return True
        self.castling[self.turn]['queen'] = False
        self.castling[self.turn]['king'] = False
        return False

    def is_square_attacked(self, row, col, color, simple=False):
        opponent = 'b' if color == 'w' else 'w'
        if simple:
            # Use current board state for simple checks
            for r in range(8):
                for c in range(8):
                    piece = self.board[r][c]
                    if piece and piece[0] == opponent:
                        original_turn = self.turn
                        self.turn = opponent
                        moves = self.get_valid_moves(c, r, simple=True)
                        self.turn = original_turn
                        if (row, col) in moves:
                            print(f"Square ({row}, {col}) attacked by {self.board[r][c]} at (row, col)=({r}, {c}) with moves {moves}")
                            return True
        else:
            # Check non-split pieces on current board
            for r in range(8):
                for c in range(8):
                    piece = self.board[r][c]
                    if piece and piece[0] == opponent and not self.split_manager.is_split_piece((r, c)):
                        original_turn = self.turn
                        self.turn = opponent
                        moves = self.get_valid_moves(c, r, simple=True)
                        self.turn = original_turn
                        if (row, col) in moves:
                            print(f"Square ({row}, {col}) attacked by non-split {piece} at (row, col)=({r}, {c}) with moves {moves}")
                            return True
            # Check split pieces by simulating each possible real position
            split_groups = self.split_manager.get_split_positions()
            for group in split_groups:
                for pos, piece in group:
                    if piece[0] == opponent:
                        # Simulate piece at pos being real
                        temp_board = copy.deepcopy(self.board)
                        # Place piece at pos, clear other split positions in group
                        temp_board[pos[0]][pos[1]] = piece
                        for other_pos, _ in group:
                            if other_pos != pos:
                                temp_board[other_pos[0]][other_pos[1]] = ''
                        original_board = self.board
                        self.board = temp_board
                        original_turn = self.turn
                        self.turn = opponent
                        moves = self.get_valid_moves(pos[1], pos[0], simple=True)
                        self.turn = original_turn
                        self.board = original_board
                        if (row, col) in moves:
                            print(f"Square ({row}, {col}) attacked by split {piece} at (row, col)=({pos[0]}, {pos[1]}) with moves {moves}")
                            return True
        print(f"Square ({row}, {col}) not attacked by any {opponent} piece")
        return False

    def is_in_check(self, color, simple=False):
        if not simple and self.check_cache[color] is not None:
            print(f"Using cached check state for {color}: {self.check_cache[color]}")
            return self.check_cache[color]
        king_pos = None
        for r in range(8):
            for c in range(8):
                if self.board[r][c] == f'{color}k':
                    king_pos = (r, c)
                    break
        if king_pos is None:
            print(f"No {color} king found on board!")
            return False
        in_check = self.is_square_attacked(king_pos[0], king_pos[1], color, simple=simple)
        print(f"King of {color} at (row, col)=({king_pos}) is {'in check' if in_check else 'not in check'}")
        if not simple and in_check:
            # Only collapse subsystems if check is confirmed
            for subsystem in self.split_manager.subsystems:
                if not subsystem.measured:
                    subsystem.collapse()
            self.split_manager.apply_collapse_to_board(self.board)
            self.invalidate_check_cache()
        if not simple:
            self.check_cache[color] = in_check
        return in_check

    def invalidate_check_cache(self):
        self.check_cache = {'w': None, 'b': None}
        print("Check cache invalidated")

    def is_checkmate(self, color):
        if not self.is_in_check(color, simple=False):
            return False
        for row in range(8):
            for col in range(8):
                piece = self.board[row][col]
                if piece and piece[0] == color:
                    moves = self.get_valid_moves(col, row, simple=False)
                    if moves:
                        for to_row, to_col in moves:
                            if self.is_legal_move(row, col, to_row, to_col):
                                return False
        return True

    def is_stalemate(self, color):
        if self.is_in_check(color, simple=False):
            return False
        for row in range(8):
            for col in range(8):
                piece = self.board[row][col]
                if piece and piece[0] == color:
                    moves = self.get_valid_moves(col, row, simple=False)
                    if moves:
                        for to_row, to_col in moves:
                            if self.is_legal_move(row, col, to_row, to_col):
                                return False
        return True

    def is_legal_move(self, from_row, from_col, to_row, to_col):
        if self.game_over or self.edit_mode:
            return False
        piece = self.board[from_row][from_col]
        captured = self.board[to_row][to_col]
        self.board[to_row][to_col] = piece
        self.board[from_row][from_col] = ''
        in_check_after_move = self.is_in_check(self.turn, simple=True)
        self.board[from_row][from_col] = piece
        self.board[to_row][to_col] = captured
        in_check_before = self.is_in_check(self.turn, simple=True)
        if in_check_before:
            self.board[to_row][to_col] = piece
            self.board[from_row][from_col] = ''
            still_in_check = self.is_in_check(self.turn, simple=True)
            self.board[from_row][from_col] = piece
            self.board[to_row][to_col] = captured
            if still_in_check:
                print(f"Move from (row, col)=({from_row}, {from_col}) to ({to_row}, {to_col}) is illegal: does not resolve check")
                return False
            else:
                print(f"Move from (row, col)=({from_row}, {from_col}) to ({to_row}, {to_col}) is legal: resolves check")
                return True
        if in_check_after_move:
            print(f"Move from (row, col)=({from_row}, {from_col}) to ({to_row}, {to_col}) is illegal: leaves king in check")
            return False
        else:
            print(f"Move from (row, col)=({from_row}, {from_col}) to ({to_row}, {to_col}) is legal")
            return True

    def make_move(self, from_row, from_col, to_row, to_col):
        if self.game_over or self.edit_mode:
            return
        piece = self.board[from_row][from_col]
        target_piece = self.board[to_row][to_col]
        is_split_from = self.split_manager.is_split_piece((from_row, from_col))
        is_split_to = self.split_manager.is_split_piece((to_row, to_col))
        is_capture = target_piece and target_piece[0] != self.turn
        is_en_passant = piece[1] == 'p' and (to_row, to_col) == self.en_passant

        # Handle moving a split piece
        if is_split_from:
            qubit_info = self.split_manager.get_qubit_for_position((from_row, from_col))
            if qubit_info:
                subsystem, qubit, branch = qubit_info
                subsystem.collapse()
                real_branch = qubit.branch_a if qubit.collapsed_result == 'a' else qubit.branch_b
                if real_branch.pos != (from_row, from_col):
                    self.split_manager.apply_collapse_to_board(self.board, qubit)
                    self.board[from_row][from_col] = ''  # Clear fake position
                    self.invalidate_check_cache()
                    self.turn = 'b' if self.turn == 'w' else 'w'
                    if self.is_checkmate(self.turn):
                        self.game_over = True
                        self.draw_by_stalemate = False
                        print(f"Checkmate! {self.turn == 'w' and 'Black' or 'White'} wins!")
                    elif self.is_stalemate(self.turn):
                        self.game_over = True
                        self.draw_by_stalemate = True
                        print("Stalemate! Game ends in a draw!")
                    return
                self.split_manager.apply_collapse_to_board(self.board, qubit)
                piece = real_branch.piece_type  # Update piece to reflect collapsed state
                self.board[from_row][from_col] = ''  # Clear origin after collapse

        # Handle target position
        if target_piece:
            if target_piece[0] == self.turn:
                if is_split_to:
                    qubit_info = self.split_manager.get_qubit_for_position((to_row, to_col))
                    if qubit_info:
                        subsystem, qubit, branch = qubit_info
                        self.split_manager.collapse_qubit(qubit)
                        real_branch = qubit.branch_a if qubit.collapsed_result == 'a' else qubit.branch_b
                        self.split_manager.apply_collapse_to_board(self.board, qubit)
                        if real_branch.pos == (to_row, to_col):
                            print(f"Cannot move to ({to_row}, {to_col}): real split piece present")
                            self.invalidate_check_cache()
                            self.turn = 'b' if self.turn == 'w' else 'w'
                            if self.is_checkmate(self.turn):
                                self.game_over = True
                                self.draw_by_stalemate = False
                                print(f"Checkmate! {self.turn == 'w' and 'Black' or 'White'} wins!")
                            elif self.is_stalemate(self.turn):
                                self.game_over = True
                                self.draw_by_stalemate = True
                                print("Stalemate! Game ends in a draw!")
                            return
                else:
                    print(f"Cannot move to ({to_row}, {to_col}): own piece present")
                    return
            else:
                # Capture
                if is_split_to:
                    qubit_info = self.split_manager.get_qubit_for_position((to_row, to_col))
                    if qubit_info:
                        subsystem, qubit, branch = qubit_info
                        self.split_manager.collapse_qubit(qubit)
                        real_branch = qubit.branch_a if qubit.collapsed_result == 'a' else qubit.branch_b
                        self.split_manager.apply_collapse_to_board(self.board, qubit)
                        if real_branch.pos == (to_row, to_col):
                            self.captured[self.turn].append(target_piece)
                            print(f"Captured real split piece {target_piece} at ({to_row}, {to_col})")
                        else:
                            print(f"Captured fake split piece at ({to_row}, {to_col}), not added to captured list")
                else:
                    self.captured[self.turn].append(target_piece)
                    print(f"Captured non-split piece {target_piece} at ({to_row}, {to_col})")

        # Handle en passant capture
        if is_en_passant:
            capture_row = to_row + (1 if self.turn == 'w' else -1)
            captured_piece = self.board[capture_row][to_col]
            if self.split_manager.is_split_piece((capture_row, to_col)):
                qubit_info = self.split_manager.get_qubit_for_position((capture_row, to_col))
                if qubit_info:
                    subsystem, qubit, branch = qubit_info
                    self.split_manager.collapse_qubit(qubit)
                    real_branch = qubit.branch_a if qubit.collapsed_result == 'a' else qubit.branch_b
                    self.split_manager.apply_collapse_to_board(self.board, qubit)
                    if real_branch.pos == (capture_row, to_col):
                        self.captured[self.turn].append(captured_piece)
                        print(f"Captured real split piece {captured_piece} via en passant at ({capture_row}, {to_col})")
                    else:
                        print(f"Captured fake split piece via en passant at ({capture_row}, {to_col}), not added to captured list")
            else:
                self.captured[self.turn].append(captured_piece)
                print(f"Captured non-split piece {captured_piece} via en passant at ({capture_row}, {to_col})")
            self.board[capture_row][to_col] = ''

        # Perform the move
        if not self.split_mode:
            self.board[from_row][from_col] = ''  # Always clear origin
            self.board[to_row][to_col] = piece
        else:
            # Split mode: keep piece at from_pos and add to to_pos
            self.board[from_row][from_col] = piece
            self.board[to_row][to_col] = piece
            self.split_manager.create_split_qubit((from_row, from_col), (to_row, to_col), piece)
            print(f"Split piece {piece} at ({from_row}, {from_col}) and ({to_row}, {to_col})")

        # Handle castling
        if piece[1] == 'k' and abs(to_col - from_col) == 2:
            if to_col > from_col:
                self.board[from_row][7] = ''
                self.board[from_row][5] = f'{self.turn}r'
            else:
                self.board[from_row][0] = ''
                self.board[from_row][3] = f'{self.turn}r'

        # Handle promotion
        if piece[1] == 'p' and (to_row == 0 or to_row == 7):
            self.promotion_pending = True
            self.promotion_pos = (to_row, to_col)
            print(f"Promotion pending at (row, col)=({to_row}, {to_col})")
            return

        # Update game state
        self.en_passant = None
        if piece[1] == 'p' and abs(to_row - from_row) == 2:
            self.en_passant = (from_row + (to_row - from_row) // 2, from_col)
        if piece[1] == 'k':
            self.castling[self.turn]['king_nm'] = False
            self.castling[self.turn]['queen_nm'] = False
        if piece[1] == 'r':
            if from_col == 0:
                self.castling[self.turn]['queen_nm'] = False
            elif from_col == 7:
                self.castling[self.turn]['king_nm'] = False
        self.turn = 'b' if self.turn == 'w' else 'w'
        self.split_mode = False
        self.history.append((from_row, from_col, to_row, to_col, piece, target_piece))
        self.invalidate_check_cache()
        if self.is_checkmate(self.turn):
            self.game_over = True
            self.draw_by_stalemate = False
            print(f"Checkmate! {self.turn == 'w' and 'Black' or 'White'} wins!")
        elif self.is_stalemate(self.turn):
            self.game_over = True
            self.draw_by_stalemate = True
            print("Stalemate! Game ends in a draw!")
        print(f"Moved {piece} from (row, col)=({from_row}, {from_col}) to ({to_row}, {to_col}), turn now: {self.turn}")

    def handle_click(self, pos):
        if self.game_over:
            return
        edit_choice = self.get_edit_choice(pos)
        if edit_choice:
            if edit_choice == 'toggle_edit':
                self.edit_mode = not self.edit_mode
                self.selected = None
                self.valid_moves = []
                self.selected_piece_to_place = None
                if not self.edit_mode:
                    if self.is_stalemate(self.turn):
                        self.game_over = True
                        self.draw_by_stalemate = True
                        print("Stalemate detected after exiting edit mode! Game ends in a draw!")
                print(f"Edit mode {'enabled' if self.edit_mode else 'disabled'}")
            else:
                self.selected_piece_to_place = edit_choice
            return
        if self.edit_mode:
            square = self.get_square(pos)
            if square:
                col, row = square
                if self.selected_piece_to_place:
                    if self.selected_piece_to_place == 'delete':
                        self.board[row][col] = ''
                        print(f"Deleted piece at (row, col)=({row}, {col})")
                    else:
                        self.board[row][col] = self.selected_piece_to_place
                        print(f"Placed {self.selected_piece_to_place} at (row, col)=({row}, {col})")
                    self.invalidate_check_cache()
            return
        if self.promotion_pending:
            choice = self.get_promotion_choice(pos)
            if choice:
                row, col = self.promotion_pos
                new_piece = f"{self.turn}{choice}"
                self.board[row][col] = new_piece
                # Update quantum state if position is split
                qubit_info = self.split_manager.get_qubit_for_position((row, col))
                if qubit_info:
                    subsystem, qubit, branch = qubit_info
                    if branch == 'a':
                        qubit.branch_a.piece_type = new_piece
                    else:
                        qubit.branch_b.piece_type = new_piece
                print(f"Promoted pawn at (row, col)=({row}, {col}) to {self.board[row][col]}")
                self.promotion_pending = False
                self.promotion_pos = None
                self.en_passant = None
                self.turn = 'b' if self.turn == 'w' else 'w'
                self.selected = None
                self.valid_moves = []
                self.invalidate_check_cache()
                if self.is_checkmate(self.turn):
                    self.game_over = True
                    self.draw_by_stalemate = False
                    print(f"Checkmate! {self.turn == 'w' and 'Black' or 'White'} wins!")
                elif self.is_stalemate(self.turn):
                    self.game_over = True
                    self.draw_by_stalemate = True
                    print("Stalemate! Game ends in a draw!")
            return
        square = self.get_square(pos)
        if not square:
            print("Click outside board")
            return
        col, row = square
        print(f"Handling click at square (row, col): ({row}, {col}), current turn: {self.turn}")
        print(f"Board at (row, col)=({row}, {col}): {self.board[row][col]}")
        print(f"Selected: {self.selected}, Valid moves: {self.valid_moves}")
        if self.selected:
            print(f"Selected piece at (col, row)=({self.selected}), valid moves: {self.valid_moves}")
            if (row, col) in self.valid_moves:
                print(f"Moving from (col, row)=({self.selected}) to ({row}, {col})")
                self.make_move(self.selected[1], self.selected[0], row, col)
                if not self.promotion_pending:
                    self.selected = None
                    self.valid_moves = []
            else:
                self.selected = None
                self.valid_moves = []
                print("Deselected piece, no valid move")
        elif self.board[row][col] and self.board[row][col][0] == self.turn:
            print(f"Piece at (row, col)=({row}, {col}) is {self.board[row][col]}, color={self.board[row][col][0]}, matches turn={self.turn}")
            self.selected = (col, row)
            self.valid_moves = self.get_valid_moves(col, row, simple=False)
            print(f"Selected {self.board[row][col]} at (row, col)=({row}, {col})")
        else:
            print(f"Cannot select piece at (row, col)=({row}, {col}): {self.board[row][col]}, turn={self.turn}")

    def update_loop(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                self.handle_click(event.pos)
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_SPACE:
                    self.split_mode = not self.split_mode
                    print(f"Split mode {'enabled' if self.split_mode else 'disabled'}")
        self.screen.fill((0, 0, 0))
        self.draw_board()
        self.draw_sidebar()
        pygame.display.flip()

def setup():
    global game
    game = ChessGame()

async def main():
    setup()
    while game.running:
        game.update_loop()
        await asyncio.sleep(1.0 / 60)

if platform.system() == "Emscripten":
    asyncio.ensure_future(main())
else:
    if __name__ == "__main__":
        asyncio.run(main())