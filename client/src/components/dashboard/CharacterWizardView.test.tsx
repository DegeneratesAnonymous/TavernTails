import React from 'react'
import { render, screen, fireEvent } from '@testing-library/react'
import CharacterWizardView from './CharacterWizardView'
import * as api from '../../api'

// Mock the api module (CRA sets resetMocks:true, so implementations must be
// set in beforeEach via mockImplementation rather than jest.fn(impl)).
jest.mock('../../api')
const mockApiFetch = api.apiFetch as jest.MockedFunction<typeof api.apiFetch>

// ---------------------------------------------------------------------------
// Shared mock data
// ---------------------------------------------------------------------------
const MOCK_WIZARD_CONFIG = {
  systems: [
    {
      name: 'D&D 5e',
      publisher: 'Wizards of the Coast',
      classes: ['Fighter', 'Rogue', 'Wizard'],
      ability_scores: [
        { key: 'str', label: 'Strength' },
        { key: 'dex', label: 'Dexterity' },
        { key: 'con', label: 'Constitution' },
        { key: 'int', label: 'Intelligence' },
        { key: 'wis', label: 'Wisdom' },
        { key: 'cha', label: 'Charisma' },
      ],
      standard_array: [15, 14, 13, 12, 10, 8],
      point_buy_budget: 27,
      point_buy_min: 8,
      point_buy_max: 15,
      questions: [
        {
          id: 'q1',
          text: 'Bandits are blocking the road. What do you do?',
          choices: [
            { id: 'a', text: 'Talk your way through', skills: ['Persuasion', 'Deception'], narrative: 'Words are your weapon.' },
            { id: 'b', text: 'Sneak around them', skills: ['Stealth'], narrative: 'Patience and cunning.' },
            { id: 'c', text: 'Confront them', skills: ['Athletics', 'Intimidation'], narrative: 'You face danger head-on.' },
          ],
        },
        {
          id: 'q5',
          text: 'Which best describes your early life?',
          choices: [
            { id: 'a', text: 'Raised among scholars', skills: ['History'], narrative: 'The city shaped you.', background: 'Sage', languages: 'Two languages' },
            { id: 'b', text: 'Grew up in the wilds', skills: ['Survival'], narrative: 'Wild places are home.', background: 'Folk Hero', languages: 'One language' },
          ],
        },
      ],
    },
    {
      name: 'Pathfinder 2e',
      publisher: 'Paizo',
      classes: ['Fighter', 'Rogue'],
      ability_scores: [
        { key: 'str', label: 'Strength' },
        { key: 'dex', label: 'Dexterity' },
      ],
      standard_array: [16, 14],
      point_buy_budget: 0,
      point_buy_min: 8,
      point_buy_max: 18,
      questions: [
        {
          id: 'q1',
          text: 'Bandits block your path. What do you do?',
          choices: [
            { id: 'a', text: 'Negotiate', skills: ['Diplomacy'], narrative: 'Words first.' },
          ],
        },
      ],
    },
  ],
}

function makeMockFetch() {
  return (url: string, options?: RequestInit): Promise<any> => {
    if (url === '/characters/wizard/config') {
      return Promise.resolve({ json: () => Promise.resolve(MOCK_WIZARD_CONFIG) })
    }
    if (url === '/characters' && options?.method === 'POST') {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ character: { id: 42, name: 'Test Hero', level: 1 } }),
      })
    }
    return Promise.resolve({ ok: false, json: () => Promise.resolve({}) })
  }
}

// ---------------------------------------------------------------------------
// Default props
// ---------------------------------------------------------------------------
const defaultProps = {
  activeSessionId: null as string | null,
  onRefreshCharacters: jest.fn() as jest.MockedFunction<() => Promise<void>>,
  onAssignCharacterToSession: jest.fn() as jest.MockedFunction<(id: number | null) => Promise<void>>,
  onSetActiveCharacterId: jest.fn(),
  onDone: jest.fn(),
  onGoToGameplay: jest.fn(),
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('CharacterWizardView', () => {
  beforeEach(() => {
    // CRA Jest config resets mocks before each test, so re-apply implementation here.
    mockApiFetch.mockImplementation(makeMockFetch())
    defaultProps.onRefreshCharacters.mockResolvedValue(undefined)
    defaultProps.onAssignCharacterToSession.mockResolvedValue(undefined)
  })

  it('renders the system selection step initially', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    expect(screen.getByText('Create Character')).toBeInTheDocument()
    expect(await screen.findByText('Choose a game system')).toBeInTheDocument()
  })

  it('shows loaded game systems', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    expect(await screen.findByText('D&D 5e')).toBeInTheDocument()
    expect(screen.getByText('Pathfinder 2e')).toBeInTheDocument()
  })

  it('disables Next button until a system is selected', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    await screen.findByText('Choose a game system')
    const nextBtn = screen.getByRole('button', { name: 'Next' })
    expect(nextBtn).toBeDisabled()
  })

  it('enables Next button after selecting a system', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    fireEvent.click(await screen.findByText('D&D 5e'))
    const nextBtn = screen.getByRole('button', { name: 'Next' })
    expect(nextBtn).not.toBeDisabled()
  })

  it('advances to basics step after selecting a system and clicking Next', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    fireEvent.click(await screen.findByText('D&D 5e'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    expect(await screen.findByText('Character basics')).toBeInTheDocument()
  })

  it('disables Next on basics step when name is empty', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    fireEvent.click(await screen.findByText('D&D 5e'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Character basics')
    const nextBtn = screen.getByRole('button', { name: 'Next' })
    expect(nextBtn).toBeDisabled()
  })

  it('advances through the full wizard in helper mode and shows review', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    // Step 1: select system
    fireEvent.click(await screen.findByText('D&D 5e'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    // Step 2: basics
    await screen.findByText('Character basics')
    fireEvent.change(screen.getByPlaceholderText('Enter character name'), { target: { value: 'Arin' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    // Step 3: abilities
    await screen.findByText('Ability scores')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    // Step 4: mode (Helper is default)
    await screen.findByText('Choose your creation style')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    // Step 5a: questionnaire — answer q1
    await screen.findByText(/Question 1/)
    fireEvent.click(screen.getByText('Talk your way through'))
    fireEvent.click(screen.getByRole('button', { name: 'Next Question' }))

    // Answer q2 (last question)
    await screen.findByText(/Question 2/)
    fireEvent.click(screen.getByText('Grew up in the wilds'))
    fireEvent.click(screen.getByRole('button', { name: 'Review Character' }))

    // Step 6: review
    expect(await screen.findByText('Review your character')).toBeInTheDocument()
  })

  it('shows step progress indicator', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    await screen.findByText('Choose a game system')
    expect(screen.getByText('System')).toBeInTheDocument()
    expect(screen.getByText('Basics')).toBeInTheDocument()
    expect(screen.getByText('Review')).toBeInTheDocument()
  })

  it('can navigate back from basics to system', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    fireEvent.click(await screen.findByText('D&D 5e'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))
    await screen.findByText('Character basics')
    fireEvent.click(screen.getByRole('button', { name: 'Back' }))
    expect(await screen.findByText('Choose a game system')).toBeInTheDocument()
  })

  it('cancels and calls onDone when Cancel is clicked', async () => {
    const onDone = jest.fn()
    render(<CharacterWizardView {...defaultProps} onDone={onDone} />)
    await screen.findByText('Choose a game system')
    fireEvent.click(screen.getAllByRole('button', { name: 'Cancel' })[0])
    expect(onDone).toHaveBeenCalled()
  })

  it('shows manual mode form when manual mode is selected', async () => {
    render(<CharacterWizardView {...defaultProps} />)
    fireEvent.click(await screen.findByText('D&D 5e'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await screen.findByText('Character basics')
    fireEvent.change(screen.getByPlaceholderText('Enter character name'), { target: { value: 'Galindra' } })
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await screen.findByText('Ability scores')
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    await screen.findByText('Choose your creation style')
    fireEvent.click(screen.getByText('✏️ Manual Mode — Full Control'))
    fireEvent.click(screen.getByRole('button', { name: 'Next' }))

    expect(await screen.findByText('Character details')).toBeInTheDocument()
  })
})
