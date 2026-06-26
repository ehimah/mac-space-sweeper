import React, {useEffect, useMemo, useState} from 'react';
import {Box, Text, useApp, useInput} from 'ink';
import zod from 'zod';
import {dedupeSelectedTargets, formatBytes, removePath, runScan, type Category, type ScanItem, type ScanResult} from '../lib/backend.js';

export const options = zod.object({
	all: zod.boolean().default(false).describe('Select all categories by default'),
	category: zod.array(zod.string()).optional().describe('Preselect one or more category keys'),
	dryRun: zod.boolean().default(false).describe('Show cleanup progress without deleting anything'),
	limit: zod.number().int().positive().default(5).describe('Number of top items to show for the active category'),
	scanOnly: zod.boolean().default(false).describe('Exit after scan and review, without cleanup'),
});

type Props = {
	options: zod.infer<typeof options>;
};

type Phase = 'scanning' | 'review' | 'cleaning' | 'done' | 'error';

type CleanupState = {
	index: number;
	freedBytes: number;
	currentItem?: ScanItem;
	errors: string[];
};

const buildBar = (ratio: number, width = 28): string => {
	const clamped = Math.max(0, Math.min(1, ratio));
	const filled = Math.round(clamped * width);
	return `${'█'.repeat(filled)}${'░'.repeat(width - filled)}`;
};

const selectedTotal = (categories: Category[], selectedKeys: Set<string>): number =>
	dedupeSelectedTargets(categories, selectedKeys).reduce((sum, item) => sum + item.sizeBytes, 0);

const helpText =
	'Up/Down move  Space toggle  a select all  r recommended  c clean  d dry run  q quit';

export default function Index({options}: Props) {
	const {exit} = useApp();
	const [phase, setPhase] = useState<Phase>('scanning');
	const [scanResult, setScanResult] = useState<ScanResult | undefined>();
	const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());
	const [cursorIndex, setCursorIndex] = useState(0);
	const [cleanupState, setCleanupState] = useState<CleanupState>({
		index: 0,
		freedBytes: 0,
		errors: [],
	});
	const [dryRun, setDryRun] = useState(options.dryRun);
	const [errorMessage, setErrorMessage] = useState<string | undefined>();

	useEffect(() => {
		let cancelled = false;

		void runScan({all: true}).then(
			result => {
				if (cancelled) {
					return;
				}

				const initialSelection = new Set<string>();
				if (options.category && options.category.length > 0) {
					for (const key of options.category) {
						if (result.categories.some(category => category.key === key)) {
							initialSelection.add(key);
						}
					}
				} else if (options.all) {
					for (const category of result.categories) {
						initialSelection.add(category.key);
					}
				} else {
					for (const category of result.categories) {
						if (category.recommended) {
							initialSelection.add(category.key);
						}
					}
				}

				setScanResult(result);
				setSelectedKeys(initialSelection);
				setPhase('review');
			},
			error => {
				if (cancelled) {
					return;
				}

				setErrorMessage(error instanceof Error ? error.message : String(error));
				setPhase('error');
			},
		);

		return () => {
			cancelled = true;
		};
	}, [options.all, options.category]);

	const categories = scanResult?.categories ?? [];
	const activeCategory = categories[cursorIndex];
	const targets = useMemo(() => dedupeSelectedTargets(categories, selectedKeys), [categories, selectedKeys]);
	const totalSelectedBytes = useMemo(() => selectedTotal(categories, selectedKeys), [categories, selectedKeys]);

	const toggleCategory = (index: number) => {
		const category = categories[index];
		if (!category) {
			return;
		}

		setSelectedKeys(previous => {
			const next = new Set(previous);
			if (next.has(category.key)) {
				next.delete(category.key);
			} else {
				next.add(category.key);
			}

			return next;
		});
	};

	const startCleanup = () => {
		if (phase !== 'review' || targets.length === 0) {
			return;
		}

		setCleanupState({
			index: 0,
			freedBytes: 0,
			errors: [],
		});
		setPhase('cleaning');
	};

	useEffect(() => {
		if (phase !== 'cleaning') {
			return;
		}

		let cancelled = false;

		const run = async () => {
			for (const [index, item] of targets.entries()) {
				if (cancelled) {
					return;
				}

				setCleanupState(previous => ({
					...previous,
					index,
					currentItem: item,
				}));

				try {
					if (!dryRun) {
						await removePath(item.path);
					} else {
						await new Promise(resolve => setTimeout(resolve, 10));
					}

					if (cancelled) {
						return;
					}

					setCleanupState(previous => ({
						...previous,
						index: index + 1,
						freedBytes: previous.freedBytes + item.sizeBytes,
						currentItem: item,
					}));
				} catch (error) {
					if (cancelled) {
						return;
					}

					const message = error instanceof Error ? error.message : String(error);
					setCleanupState(previous => ({
						...previous,
						index: index + 1,
						currentItem: item,
						errors: [...previous.errors, `${item.path}: ${message}`],
					}));
				}
			}

			if (!cancelled) {
				setPhase('done');
			}
		};

		void run();

		return () => {
			cancelled = true;
		};
	}, [dryRun, phase, targets]);

	useInput((input, key) => {
		if (phase === 'review') {
			if (key.upArrow) {
				setCursorIndex(previous => Math.max(0, previous - 1));
				return;
			}

			if (key.downArrow) {
				setCursorIndex(previous => Math.min(categories.length - 1, previous + 1));
				return;
			}

			if (input === ' ') {
				toggleCategory(cursorIndex);
				return;
			}

			if (input === 'a') {
				setSelectedKeys(new Set(categories.map(category => category.key)));
				return;
			}

			if (input === 'r') {
				setSelectedKeys(
					new Set(categories.filter(category => category.recommended).map(category => category.key)),
				);
				return;
			}

			if (input === 'd') {
				setDryRun(previous => !previous);
				return;
			}

			if (input === 'c' || key.return) {
				if (options.scanOnly) {
					exit();
					return;
				}

				startCleanup();
				return;
			}
		}

		if (input === 'q' || (phase === 'done' && key.return)) {
			exit();
		}
	});

	if (phase === 'scanning') {
		return (
			<Box flexDirection="column">
				<Text color="cyan">Scanning macOS junk categories...</Text>
				<Text dimColor>Python backend: {dryRun ? 'dry-run mode armed' : 'live cleanup mode armed'}</Text>
			</Box>
		);
	}

	if (phase === 'error') {
		return (
			<Box flexDirection="column">
				<Text color="red">Scan failed.</Text>
				{errorMessage && <Text>{errorMessage}</Text>}
				<Text dimColor>Press q to quit.</Text>
			</Box>
		);
	}

	if (phase === 'cleaning') {
		const ratio = targets.length === 0 ? 0 : cleanupState.index / targets.length;
		return (
			<Box flexDirection="column">
				<Text color={dryRun ? 'yellow' : 'green'}>
					{dryRun ? 'Dry run in progress' : 'Cleanup in progress'}
				</Text>
				<Text>
					{buildBar(ratio)} {Math.round(ratio * 100)}%
				</Text>
				<Text>
					Processed {cleanupState.index}/{targets.length} items
				</Text>
				<Text>Freed so far: {formatBytes(cleanupState.freedBytes)}</Text>
				{cleanupState.currentItem && (
					<Text>
						Current: {cleanupState.currentItem.name} ({cleanupState.currentItem.sizeHuman})
					</Text>
				)}
				{cleanupState.errors.length > 0 && (
					<Text color="red">Errors so far: {cleanupState.errors.length}</Text>
				)}
				<Text dimColor>Press q to exit when the pass completes.</Text>
			</Box>
		);
	}

	if (phase === 'done') {
		return (
			<Box flexDirection="column">
				<Text color="green">{dryRun ? 'Dry run complete.' : 'Cleanup complete.'}</Text>
				<Text>Processed: {targets.length} items</Text>
				<Text>{dryRun ? 'Would free' : 'Freed'}: {formatBytes(cleanupState.freedBytes)}</Text>
				{cleanupState.errors.length > 0 && (
					<>
						<Text color="red">Errors: {cleanupState.errors.length}</Text>
						{cleanupState.errors.slice(0, 5).map(error => (
							<Text key={error}>{error}</Text>
						))}
					</>
				)}
				<Text dimColor>Press Enter or q to exit.</Text>
			</Box>
		);
	}

	const visibleItems = activeCategory?.items.slice(0, options.limit) ?? [];
	return (
		<Box flexDirection="column">
			<Text color="cyan">mac-junk-cleaner TUI</Text>
			<Text>
				Selected: {selectedKeys.size} categories, {targets.length} unique targets, {formatBytes(totalSelectedBytes)}
			</Text>
			<Text color={dryRun ? 'yellow' : 'green'}>
				Mode: {dryRun ? 'dry-run' : 'live cleanup'}
			</Text>
			<Text dimColor>{helpText}</Text>
			<Box marginTop={1} flexDirection="column">
				{categories.map((category, index) => {
					const focused = index === cursorIndex;
					const checked = selectedKeys.has(category.key);
					return (
						<Text key={category.key} color={focused ? 'cyan' : undefined}>
							{focused ? '›' : ' '} {checked ? '[x]' : '[ ]'} {category.label} ({category.totalHuman})
							{category.recommended ? ' recommended' : ''}
						</Text>
					);
				})}
			</Box>
			{activeCategory && (
				<Box marginTop={1} flexDirection="column">
					<Text color="magenta">
						{activeCategory.label} [{activeCategory.key}]
					</Text>
					<Text>{activeCategory.description}</Text>
					<Text>Top items:</Text>
					{visibleItems.length === 0 ? (
						<Text dimColor>No items.</Text>
					) : (
						visibleItems.map(item => (
							<Text key={item.path}>
								- {item.sizeHuman} {item.path}
							</Text>
						))
					)}
				</Box>
			)}
		</Box>
	);
}
