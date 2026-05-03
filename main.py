import os
import json
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler
from dotenv import load_dotenv
from typing import Optional, Dict, List, Any, Tuple
from enum import Enum

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv('BOT_TOKEN')

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ============================================================================
# DATABASE & CONSTANTS
# ============================================================================

PC_DATABASE: Dict[str, Any] = {}

# Conversation states
BUDGET = 0
BUILD_TYPE = 1
UPGRADE_MENU = 2
UPGRADE_SELECTION = 3

class BuildType(Enum):
    """Build type enumeration."""
    GAMING = 'gaming'
    CONTENT_CREATION = 'content_creation'

# ============================================================================
# BUILD CONFIGURATION WITH BALANCED ALLOCATION
# ============================================================================

BUILD_CONFIGS = {
    'gaming': {
        'description': '🎮 Gaming Build',
        'budget_allocation': {
            'gpu': 0.45,
            'cpu': 0.16,
            'motherboard': 0.08,
            'ram': 0.10,
            'cooler': 0.04,
            'storage': 0.08,
            'case': 0.03,
            'psu': 0.06
        },
        'gpu_weight': 0.50,
        'cpu_weight': 0.30,
        'performance_emphasis': 'gpu'
    },
    'content_creation': {
        'description': '🎬 Content Creation Build',
        'budget_allocation': {
            'cpu': 0.30,
            'ram': 0.25,
            'gpu': 0.18,
            'motherboard': 0.10,
            'cooler': 0.08,
            'storage': 0.05,
            'case': 0.02,
            'psu': 0.02
        },
        'gpu_weight': 0.25,
        'cpu_weight': 0.60,
        'performance_emphasis': 'cpu'
    }
}

# GPU Tier system for balance checking
class GPUTier(Enum):
    """GPU performance tiers."""
    ENTRY = 1
    MAINSTREAM = 2
    HIGH_END = 3
    FLAGSHIP = 4

GPU_TIER_MAPPING = {
    'RTX 5050': GPUTier.ENTRY,
    'RTX 5060': GPUTier.ENTRY,
    'RTX 5070': GPUTier.MAINSTREAM,
    'RTX 5070 Ti': GPUTier.MAINSTREAM,
    'RTX 5080': GPUTier.HIGH_END,
    'RTX 5090': GPUTier.FLAGSHIP,
}

# CPU Tier system for balance checking
class CPUTier(Enum):
    """CPU performance tiers."""
    ENTRY = 1
    MID_RANGE = 2
    HIGH_END = 3
    FLAGSHIP = 4

CPU_TIER_MAPPING = {
    'Core i5-14400F': CPUTier.ENTRY,
    'Core i5-14600K': CPUTier.ENTRY,
    'Core i5-14600KF': CPUTier.ENTRY,
    'Core i7-14700F': CPUTier.MID_RANGE,
    'Core i7-14700K': CPUTier.MID_RANGE,
    'Core i7-14700KF': CPUTier.MID_RANGE,
    'Core i9-14900F': CPUTier.HIGH_END,
    'Core i9-14900K': CPUTier.HIGH_END,
    'Core i9-14900KF': CPUTier.HIGH_END,
    'Core i9-14900KS': CPUTier.FLAGSHIP,
    'Ryzen 5 7600': CPUTier.ENTRY,
    'Ryzen 5 7600X': CPUTier.ENTRY,
    'Ryzen 5 9600X': CPUTier.ENTRY,
    'Ryzen 7 7700': CPUTier.MID_RANGE,
    'Ryzen 7 7700X': CPUTier.MID_RANGE,
    'Ryzen 7 9700X': CPUTier.MID_RANGE,
    'Ryzen 9 7900X': CPUTier.HIGH_END,
    'Ryzen 9 9900X': CPUTier.HIGH_END,
    'Ryzen 9 7950X': CPUTier.FLAGSHIP,
    'Ryzen 9 9950X': CPUTier.FLAGSHIP,
}

# Motherboard tier mapping
MOTHERBOARD_TIER_MAPPING = {
    'H610': 1,
    'H770': 2,
    'Z790': 3,
    'B850': 2,
    'X870': 3,
    'X870-E': 4,
}

# ============================================================================
# BALANCE RULES ENGINE
# ============================================================================

class BalanceValidator:
    """Validates and enforces build balance."""

    @staticmethod
    def get_gpu_tier(gpu: Dict) -> GPUTier:
        """Get GPU tier from model name."""
        for tier_gpu, tier in GPU_TIER_MAPPING.items():
            if tier_gpu in gpu['model']:
                return tier
        return GPUTier.ENTRY

    @staticmethod
    def get_cpu_tier(cpu: Dict) -> CPUTier:
        """Get CPU tier from model name."""
        for tier_cpu, tier in CPU_TIER_MAPPING.items():
            if tier_cpu in cpu['model']:
                return tier
        return CPUTier.MID_RANGE

    @staticmethod
    def get_motherboard_tier(motherboard: Dict) -> int:
        """Get motherboard tier from chipset."""
        chipset = motherboard.get('chipset', '')
        for chip, tier in MOTHERBOARD_TIER_MAPPING.items():
            if chip in chipset:
                return tier
        return 2

    @staticmethod
    def is_balanced(cpu: Dict, gpu: Dict, motherboard: Dict, build_type: str) -> Tuple[bool, str]:
        """Check if build is balanced."""
        cpu_tier = BalanceValidator.get_cpu_tier(cpu)
        gpu_tier = BalanceValidator.get_gpu_tier(gpu)
        mobo_tier = BalanceValidator.get_motherboard_tier(motherboard)

        if build_type == 'gaming':
            if gpu_tier.value < cpu_tier.value - 1:
                return False, f"GPU tier ({gpu_tier.name}) is too low for CPU tier ({cpu_tier.name})"

        if build_type == 'content_creation':
            if cpu_tier.value < gpu_tier.value - 1:
                return False, f"CPU tier ({cpu_tier.name}) is too low for GPU tier ({gpu_tier.name})"

        if build_type == 'gaming':
            if mobo_tier > cpu_tier.value + 1:
                return False, f"Motherboard is overkill for CPU tier ({cpu_tier.name})"

        return True, "Build is balanced"

    @staticmethod
    def get_min_gpu_tier_for_budget(budget: int, build_type: str) -> GPUTier:
        """Determine minimum GPU tier required for budget."""
        if budget < 1000:
            return GPUTier.ENTRY
        elif budget < 2000:
            return GPUTier.MAINSTREAM
        elif budget < 3500:
            return GPUTier.HIGH_END
        else:
            return GPUTier.FLAGSHIP if build_type == 'gaming' else GPUTier.HIGH_END

# ============================================================================
# PERFORMANCE SCORING ENGINE
# ============================================================================

class PerformanceScorer:
    """Scores components based on performance and build type."""

    @staticmethod
    def score_gpu(gpu: Dict, config: Dict) -> float:
        """Score GPU performance."""
        score = 0.0
        
        score += gpu.get('memory_gb', 8) * 3
        
        pcie_gen = gpu.get('pcie_gen', 3)
        score += (pcie_gen - 3) * 15
        
        if 'GDDR7' in gpu.get('memory_type', ''):
            score += 20
        elif 'GDDR6' in gpu.get('memory_type', ''):
            score += 10
        
        tier = BalanceValidator.get_gpu_tier(gpu)
        score += tier.value * 50
        
        return score * config.get('gpu_weight', 0.5)

    @staticmethod
    def score_cpu(cpu: Dict, config: Dict) -> float:
        """Score CPU performance."""
        score = 0.0
        
        score += cpu.get('cores', 8) * 5
        score += cpu.get('threads', 16) * 2
        score += cpu.get('boost_ghz', 4.0) * 15
        
        tier = BalanceValidator.get_cpu_tier(cpu)
        score += tier.value * 40
        
        return score * config.get('cpu_weight', 0.3)

    @staticmethod
    def score_motherboard(motherboard: Dict) -> float:
        """Score motherboard features."""
        score = 0.0
        
        score += motherboard.get('m2_slots', 3) * 10
        score += (motherboard.get('max_memory_speed', 3200) - 3200) * 0.05
        
        tier = BalanceValidator.get_motherboard_tier(motherboard)
        score += tier * 20
        
        return score

    @staticmethod
    def score_ram(ram: Dict) -> float:
        """Score RAM performance."""
        score = 0.0
        
        score += ram.get('capacity_gb', 16) * 5
        score += ram.get('speed_mhz', 3200) * 0.01
        
        cas = ram.get('cas_latency', 16)
        score += (20 - cas) * 3
        
        return score

    @staticmethod
    def calculate_overall_score(build: Dict, config: Dict) -> float:
        """Calculate overall build performance score."""
        if not build.get('gpu') or not build.get('cpu'):
            return 0.0

        score = 0.0
        score += PerformanceScorer.score_gpu(build['gpu'], config)
        score += PerformanceScorer.score_cpu(build['cpu'], config)
        score += PerformanceScorer.score_motherboard(build['motherboard']) * 0.2
        score += PerformanceScorer.score_ram(build['ram']) * 0.15
        
        return score

# ============================================================================
# DATABASE LOADER
# ============================================================================

def load_database() -> bool:
    """Load PC parts database."""
    try:
        with open('pc-part-db.json', 'r') as f:
            global PC_DATABASE
            PC_DATABASE = json.load(f)
        logger.info("✅ PC Database loaded successfully")
        return True
    except FileNotFoundError:
        logger.error("❌ pc-part-db.json not found!")
        return False
    except json.JSONDecodeError:
        logger.error("❌ pc-part-db.json is not valid JSON!")
        return False

# ============================================================================
# COMPONENT SELECTION ENGINE
# ============================================================================

class ComponentSelector:
    """Handles intelligent component selection with cost optimization & balance enforcement."""

    @staticmethod
    def _get_components_by_type(component_type: str, param: Any = None) -> List[Dict]:
        """Get available components by type with optional filtering."""
        try:
            if component_type == 'cpu':
                if param == 'gaming':
                    return PC_DATABASE['categories']['intel_14th_gen_cpus']
                elif param == 'content_creation':
                    return PC_DATABASE['categories']['amd_ryzen_8000_cpus']
            
            elif component_type == 'motherboard':
                if param == 'LGA1700':
                    return PC_DATABASE['categories']['intel_motherboards']
                elif param == 'AM5':
                    return PC_DATABASE['categories']['amd_motherboards']
            
            elif component_type == 'ram':
                all_ram = PC_DATABASE['categories']['memory_ram']
                return [r for r in all_ram if r['type'] == param]
            
            elif component_type == 'cooler':
                all_coolers = PC_DATABASE['categories']['cpu_coolers']
                socket, tdp = param['socket'], param['tdp']
                candidates = [c for c in all_coolers if socket in c['socket']]
                return sorted(candidates, key=lambda x: x['price_usd'])
            
            elif component_type == 'gpu':
                return PC_DATABASE['categories']['nvidia_rtx_5000_gpus']
            
            elif component_type == 'storage':
                return PC_DATABASE['categories']['storage_drives']
            
            elif component_type == 'case':
                all_cases = PC_DATABASE['categories']['pc_cases']
                form_factor = param.get('motherboard_form_factor')
                candidates = [c for c in all_cases if form_factor in c['motherboard_support']]
                return candidates if candidates else all_cases
            
            elif component_type == 'psu':
                all_psus = PC_DATABASE['categories']['power_supply_units']
                required_wattage = param
                min_wattage = int(required_wattage * 0.8)
                candidates = [p for p in all_psus if p['wattage'] >= min_wattage]
                return sorted(candidates, key=lambda x: x['price_usd'])
            
            return []
        except Exception as e:
            logger.error(f"Error getting components for {component_type}: {str(e)}")
            return []

    @staticmethod
    def score_price_efficiency(component: Dict, component_type: str) -> float:
        """Score price efficiency (performance per dollar)."""
        price = component.get('price_usd', 1)
        
        if component_type == 'gpu':
            vram_score = component.get('memory_gb', 8)
            pcie_score = component.get('pcie_gen', 3) * 0.5
            gddr_bonus = 1.5 if 'GDDR7' in component.get('memory_type', '') else 1.0
            total_performance = (vram_score + pcie_score) * gddr_bonus
            return total_performance / price
        
        elif component_type == 'cpu':
            cores_score = component.get('cores', 8)
            boost_score = component.get('boost_ghz', 4.0) * 0.5
            total_performance = cores_score + boost_score
            return total_performance / price
        
        elif component_type == 'ram':
            capacity = component.get('capacity_gb', 16)
            speed = component.get('speed_mhz', 3200) / 1000
            cas = component.get('cas_latency', 16)
            cas_efficiency = 1 / (cas / 15)
            total_performance = (capacity + speed) * cas_efficiency
            return total_performance / price
        
        elif component_type == 'storage':
            capacity = component.get('capacity_gb', 512)
            speed = component.get('seq_read_mbs', 5000) / 1000
            total_performance = capacity + speed
            return total_performance / price
        
        elif component_type == 'motherboard':
            m2_slots = component.get('m2_slots', 3)
            max_speed = component.get('max_memory_speed', 3200)
            total_performance = m2_slots + (max_speed / 1000)
            return total_performance / price
        
        elif component_type == 'cooler':
            tdp = component.get('tdp_rating', 150)
            return tdp / price
        
        elif component_type == 'psu':
            wattage = component.get('wattage', 650)
            efficiency_bonus = 1.2 if '80+ Platinum' in component.get('efficiency_rating', '') else \
                              1.1 if '80+ Gold' in component.get('efficiency_rating', '') else 1.0
            total_performance = wattage * efficiency_bonus
            return total_performance / price
        
        elif component_type == 'case':
            gpu_length = component.get('max_gpu_length_mm', 350)
            return gpu_length / price
        
        return 1.0 / price

    @staticmethod
    def select_component(
        component_type: str,
        param: Any,
        max_price: int,
        available_budget: int,
        performance_score_fn: Optional[callable] = None,
        prefer_higher: bool = True
    ) -> Optional[Dict]:
        """Select best component within strict budget constraints."""
        components = ComponentSelector._get_components_by_type(component_type, param)
        
        if not components:
            logger.warning(f"No components found for {component_type}")
            return None
        
        strict_budget = min(max_price, available_budget)
        affordable = [c for c in components if c['price_usd'] <= strict_budget]
        
        if not affordable:
            logger.warning(f"No affordable {component_type} found within ${strict_budget}. Relaxing constraints...")
            affordable = sorted(components, key=lambda x: x['price_usd'])[:5]
            if not affordable:
                return None
        
        logger.info(f"Found {len(affordable)} affordable {component_type}s within ${strict_budget}")
        
        if performance_score_fn:
            affordable_with_scores = [
                (c, performance_score_fn(c))
                for c in affordable
            ]
            affordable_with_scores.sort(key=lambda x: (-x[1], x[0]['price_usd']))
            selected = affordable_with_scores[0][0]
            logger.debug(f"Selected {component_type} via custom scoring: {selected.get('model')} (${selected['price_usd']})")
        
        else:
            scored_components = [
                (c, ComponentSelector.score_price_efficiency(c, component_type))
                for c in affordable
            ]
            
            scored_components.sort(key=lambda x: (-x[1], x[0]['price_usd']))
            
            selected = scored_components[0][0]
            efficiency = scored_components[0][1]
            
            logger.debug(
                f"Selected {component_type}: {selected.get('model')} "
                f"(${selected['price_usd']}, efficiency: {efficiency:.3f})"
            )
        
        return selected

# ============================================================================
# BUILD GENERATOR
# ============================================================================

class BuildGenerator:
    """Generates PC builds with strict balance enforcement."""

    @staticmethod
    def generate(
        budget: int,
        build_type: str,
        allocations: Dict[str, float]
    ) -> Dict[str, Any]:
        """Generate a balanced PC build within budget."""
        build = {
            'cpu': None,
            'motherboard': None,
            'ram': None,
            'cooler': None,
            'gpu': None,
            'storage_primary': None,
            'case': None,
            'psu': None,
            'total_cost': 0,
            'remaining_budget': budget,
            'budget_allocation': allocations,
            'total_power_consumption': 0,
            'error_message': None,
            'balance_warnings': [],
            'performance_score': 0.0
        }
        
        spent = 0
        selector = ComponentSelector()
        config = BUILD_CONFIGS[build_type]
        
        try:
            logger.info(f"Starting balanced build: budget=${budget}, type={build_type}")
            
            # ===== STEP 1: SELECT GPU FIRST =====
            gpu_max = int(budget * allocations['gpu'] * 1.3)
            min_gpu_tier = BalanceValidator.get_min_gpu_tier_for_budget(budget, build_type)
            
            gpu = selector.select_component('gpu', None, gpu_max, budget - spent)
            if not gpu:
                build['error_message'] = "No GPU found within budget constraints."
                return build
            
            build['gpu'] = gpu
            spent += gpu['price_usd']
            gpu_tier = BalanceValidator.get_gpu_tier(gpu)
            logger.info(f"GPU: {gpu['model']} (Tier: {gpu_tier.name}, ${gpu['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 2: SELECT CPU BALANCED WITH GPU =====
            cpu_max = int(budget * allocations['cpu'] * 1.3)
            
            all_cpus = ComponentSelector._get_components_by_type('cpu', build_type)
            
            balanced_cpus = []
            for cpu in all_cpus:
                cpu_tier = BalanceValidator.get_cpu_tier(cpu)
                if abs(cpu_tier.value - gpu_tier.value) <= 1:
                    if cpu['price_usd'] <= cpu_max:
                        balanced_cpus.append(cpu)
            
            if balanced_cpus:
                balanced_cpus.sort(key=lambda x: (
                    -BalanceValidator.get_cpu_tier(x).value,
                    -x['cores'],
                    x['price_usd']
                ))
                cpu = balanced_cpus[0]
            else:
                cpu = selector.select_component('cpu', build_type, cpu_max, budget - spent)
            
            if not cpu:
                build['error_message'] = "No CPU found within budget constraints."
                return build
            
            build['cpu'] = cpu
            spent += cpu['price_usd']
            cpu_tier = BalanceValidator.get_cpu_tier(cpu)
            logger.info(f"CPU: {cpu['model']} (Tier: {cpu_tier.name}, ${cpu['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 3: SELECT MOTHERBOARD =====
            mobo_max = int(budget * allocations['motherboard'] * 1.5)
            all_mobos = ComponentSelector._get_components_by_type('motherboard', cpu['socket'])
            
            balanced_mobos = []
            for mobo in all_mobos:
                mobo_tier = BalanceValidator.get_motherboard_tier(mobo)
                if mobo_tier <= cpu_tier.value + 1 and mobo['price_usd'] <= mobo_max:
                    balanced_mobos.append(mobo)
            
            if balanced_mobos:
                balanced_mobos.sort(key=lambda x: (
                    -BalanceValidator.get_motherboard_tier(x),
                    -x['m2_slots'],
                    x['price_usd']
                ))
                mobo = balanced_mobos[0]
            else:
                mobo = selector.select_component('motherboard', cpu['socket'], mobo_max, budget - spent)
            
            if not mobo:
                build['error_message'] = "No compatible motherboard found."
                return build
            
            build['motherboard'] = mobo
            spent += mobo['price_usd']
            mobo_tier = BalanceValidator.get_motherboard_tier(mobo)
            logger.info(f"Motherboard: {mobo['model']} (Tier: {mobo_tier}, ${mobo['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 4: SELECT RAM =====
            ram_max = int(budget * allocations['ram'] * 1.3)
            ram = selector.select_component(
                'ram',
                mobo['memory_type'],
                ram_max,
                budget - spent,
                performance_score_fn=PerformanceScorer.score_ram
            )
            if not ram:
                build['error_message'] = "No compatible RAM found."
                return build
            
            build['ram'] = ram
            spent += ram['price_usd']
            logger.info(f"RAM: {ram['model']} (${ram['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 5: SELECT COOLER =====
            cooler_max = int(budget * allocations['cooler'] * 2.0)
            cooler = selector.select_component(
                'cooler',
                {'socket': cpu['socket'], 'tdp': cpu['tdp']},
                cooler_max,
                budget - spent
            )
            if not cooler:
                build['error_message'] = "No compatible CPU cooler found."
                return build
            
            build['cooler'] = cooler
            spent += cooler['price_usd']
            logger.info(f"Cooler: {cooler['model']} (${cooler['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 6: SELECT STORAGE =====
            storage_max = int(budget * allocations['storage'] * 1.3)
            storage = selector.select_component(
                'storage',
                None,
                storage_max,
                budget - spent - 200
            )
            if not storage:
                build['error_message'] = "No storage drive found."
                return build
            
            build['storage_primary'] = storage
            spent += storage['price_usd']
            logger.info(f"Storage: {storage['model']} (${storage['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 7: SELECT CASE =====
            case_max = int(budget * allocations['case'] * 2.0)
            case = selector.select_component(
                'case',
                {'motherboard_form_factor': mobo['form_factor']},
                case_max,
                budget - spent - 100
            )
            if not case:
                build['error_message'] = "No suitable case found."
                return build
            
            build['case'] = case
            spent += case['price_usd']
            logger.info(f"Case: {case['model']} (${case['price_usd']}) - Spent: ${spent}")
            
            # ===== STEP 8: SELECT PSU =====
            total_tdp = cpu['tdp'] + gpu['tdp']
            required_wattage = int(total_tdp * 1.3) + 100
            
            psu_max = budget - spent
            psu = selector.select_component('psu', required_wattage, psu_max, psu_max)
            
            if not psu:
                estimated_cost = min(psu_max, max(80, int(required_wattage * 0.12)))
                psu = {
                    'id': 'psu_estimated',
                    'brand': 'Generic',
                    'model': f'{required_wattage}W 80+ Bronze',
                    'wattage': required_wattage,
                    'efficiency_rating': '80+ Bronze',
                    'modular_type': 'Fully Modular',
                    'price_usd': estimated_cost
                }
            
            build['psu'] = psu
            spent += psu['price_usd']
            logger.info(f"PSU: {psu['model']} (${psu['price_usd']}) - Spent: ${spent}")
            
            # ===== FINAL BALANCE CHECK =====
            build['total_power_consumption'] = total_tdp
            build['total_cost'] = spent
            build['remaining_budget'] = max(0, budget - spent)
            build['performance_score'] = PerformanceScorer.calculate_overall_score(build, config)
            
            is_balanced, reason = BalanceValidator.is_balanced(cpu, gpu, mobo, build_type)
            if not is_balanced:
                build['balance_warnings'].append(f"⚠️ {reason}")
                logger.warning(f"Balance warning: {reason}")
            
            logger.info(f"✅ Balanced build complete: ${spent}/${budget} (Score: {build['performance_score']:.1f})")
            return build
            
        except Exception as e:
            logger.error(f"Build generation error: {str(e)}")
            build['error_message'] = f"An error occurred: {str(e)}"
            return build

# ============================================================================
# UPGRADE OPTIONS ENGINE (IMPROVED)
# ============================================================================

class UpgradeEngine:
    """Generates upgrade options for individual PC components with compatibility checking."""

    @staticmethod
    def get_compatible_upgrades(current_build: Dict, component_type: str, budget: int) -> Optional[List[Dict]]:
        """Get compatible upgrade options for a specific component type."""
        current_component = current_build.get(component_type)
        if not current_component:
            logger.warning(f"No current component found for {component_type}")
            return None
        
        current_price = current_component['price_usd']
        # Calculate remaining budget considering current component
        current_build_cost = current_build['total_cost']
        remaining_budget = budget - (current_build_cost - current_price)
        
        logger.info(f"Component: {component_type}")
        logger.info(f"Current price: ${current_price}")
        logger.info(f"Build cost: ${current_build_cost}")
        logger.info(f"Remaining budget: ${remaining_budget}")
        
        selector = ComponentSelector()
        compatible = []
        
        try:
            if component_type == 'gpu':
                all_options = selector._get_components_by_type('gpu', None)
                if not all_options:
                    logger.warning("No GPUs found in database")
                    return None
                
                logger.info(f"Total GPUs in database: {len(all_options)}")
                
                # Filter: must be more expensive (upgrade) and within budget
                for g in all_options:
                    if g['price_usd'] > current_price and g['price_usd'] <= remaining_budget:
                        compatible.append(g)
                
                logger.info(f"Compatible GPU options: {len(compatible)}")
                for g in compatible:
                    logger.debug(f"  - {g['model']} (${g['price_usd']}, {g['memory_gb']}GB)")
                
                # Sort by price first (logical progression), then by tier, then by VRAM
                compatible.sort(key=lambda x: (x['price_usd'], -BalanceValidator.get_gpu_tier(x).value, -x['memory_gb']))
            
            elif component_type == 'cpu':
                build_type = current_build.get('build_type', 'gaming')
                all_options = selector._get_components_by_type('cpu', build_type)
                if not all_options:
                    logger.warning("No CPUs found in database")
                    return None
                
                logger.info(f"Total CPUs in database: {len(all_options)}")
                
                # Filter: same socket, more expensive, within budget
                cpu_socket = current_build['motherboard']['socket']
                for c in all_options:
                    if (c['socket'] == cpu_socket and 
                        c['price_usd'] > current_price and 
                        c['price_usd'] <= remaining_budget):
                        compatible.append(c)
                
                logger.info(f"Compatible CPU options: {len(compatible)}")
                for c in compatible:
                    logger.debug(f"  - {c['model']} (${c['price_usd']}, {c['cores']}C)")
                
                # Sort by price first (logical progression), then by tier, then by cores
                compatible.sort(key=lambda x: (x['price_usd'], -BalanceValidator.get_cpu_tier(x).value, -x['cores']))
            
            elif component_type == 'ram':
                all_options = selector._get_components_by_type('ram', current_build['motherboard']['memory_type'])
                if not all_options:
                    logger.warning("No RAM found in database")
                    return None
                
                logger.info(f"Total RAM options in database: {len(all_options)}")
                
                current_capacity = current_component['capacity_gb']
                current_speed = current_component['speed_mhz']
                
                # Filter: more capacity OR better speed, and within budget
                for r in all_options:
                    if r['price_usd'] <= remaining_budget and r['price_usd'] > current_price:
                        if (r['capacity_gb'] > current_capacity or 
                            (r['capacity_gb'] == current_capacity and r['speed_mhz'] > current_speed)):
                            compatible.append(r)
                
                logger.info(f"Compatible RAM options: {len(compatible)}")
                for r in compatible:
                    logger.debug(f"  - {r['model']} (${r['price_usd']}, {r['capacity_gb']}GB @ {r['speed_mhz']}MHz)")
                
                # Sort by capacity first, then speed, then price
                compatible.sort(key=lambda x: (x['capacity_gb'], -x['speed_mhz'], x['price_usd']))
            
            elif component_type == 'cooler':
                all_options = selector._get_components_by_type('cooler', 
                    {'socket': current_build['cpu']['socket'], 'tdp': current_build['cpu']['tdp']})
                if not all_options:
                    logger.warning("No coolers found in database")
                    return None
                
                logger.info(f"Total coolers in database: {len(all_options)}")
                
                current_tdp = current_component['tdp_rating']
                
                # Filter: better TDP rating, within budget
                for c in all_options:
                    if c['tdp_rating'] > current_tdp and c['price_usd'] <= remaining_budget:
                        compatible.append(c)
                
                logger.info(f"Compatible cooler options: {len(compatible)}")
                for c in compatible:
                    logger.debug(f"  - {c['model']} (${c['price_usd']}, {c['tdp_rating']}W)")
                
                # Sort by TDP, then price
                compatible.sort(key=lambda x: (x['tdp_rating'], x['price_usd']))
            
            elif component_type == 'storage_primary':
                all_options = selector._get_components_by_type('storage', None)
                if not all_options:
                    logger.warning("No storage found in database")
                    return None
                
                logger.info(f"Total storage options in database: {len(all_options)}")
                
                current_capacity = current_component['capacity_gb']
                current_speed = current_component['seq_read_mbs']
                
                # Filter: larger capacity OR better speed, within budget
                for s in all_options:
                    if s['price_usd'] <= remaining_budget and s['price_usd'] > current_price:
                        if (s['capacity_gb'] > current_capacity or 
                            (s['capacity_gb'] == current_capacity and s['seq_read_mbs'] > current_speed)):
                            compatible.append(s)
                
                logger.info(f"Compatible storage options: {len(compatible)}")
                for s in compatible:
                    logger.debug(f"  - {s['model']} (${s['price_usd']}, {s['capacity_gb']}GB @ {s['seq_read_mbs']}MB/s)")
                
                # Sort by capacity, then speed, then price
                compatible.sort(key=lambda x: (x['capacity_gb'], -x['seq_read_mbs'], x['price_usd']))
            
            elif component_type == 'psu':
                all_options = selector._get_components_by_type('psu', current_build['total_power_consumption'])
                if not all_options:
                    logger.warning("No PSUs found in database")
                    return None
                
                logger.info(f"Total PSUs in database: {len(all_options)}")
                
                current_wattage = current_component['wattage']
                
                # Filter: higher wattage, within budget
                for p in all_options:
                    if (p['wattage'] >= current_wattage and 
                        p['price_usd'] <= remaining_budget and
                        p['price_usd'] > current_price):
                        compatible.append(p)
                
                logger.info(f"Compatible PSU options: {len(compatible)}")
                for p in compatible:
                    logger.debug(f"  - {p['model']} (${p['price_usd']}, {p['wattage']}W)")
                
                # Sort by wattage, then price
                compatible.sort(key=lambda x: (x['wattage'], x['price_usd']))
            
            else:
                logger.warning(f"Unknown component type: {component_type}")
                return None
            
            if not compatible:
                logger.warning(f"No compatible upgrades found for {component_type}")
                return None
            
            # Return top 3 options
            result = compatible[:3]
            logger.info(f"Returning {len(result)} upgrade options for {component_type}")
            return result
        
        except Exception as e:
            logger.error(f"Error getting compatible upgrades for {component_type}: {str(e)}")
            return None

    @staticmethod
    def apply_upgrade(current_build: Dict, component_type: str, new_component: Dict, budget: int) -> Optional[Dict]:
        """Apply an upgrade to the build and recalculate totals."""
        try:
            upgraded_build = current_build.copy()
            upgraded_build[component_type] = new_component
            
            # Recalculate total cost
            upgraded_build['total_cost'] = sum([
                upgraded_build[k]['price_usd']
                for k in ['cpu', 'motherboard', 'ram', 'cooler', 'gpu', 'storage_primary', 'case', 'psu']
                if upgraded_build.get(k)
            ])
            
            if upgraded_build['total_cost'] > budget:
                logger.warning(f"Upgrade would exceed budget: ${upgraded_build['total_cost']} > ${budget}")
                return None
            
            upgraded_build['remaining_budget'] = budget - upgraded_build['total_cost']
            
            # Recalculate performance score
            config = BUILD_CONFIGS[current_build.get('build_type', 'gaming')]
            upgraded_build['performance_score'] = PerformanceScorer.calculate_overall_score(upgraded_build, config)
            
            logger.info(f"Upgrade applied successfully. New total: ${upgraded_build['total_cost']}")
            return upgraded_build
        
        except Exception as e:
            logger.error(f"Error applying upgrade: {str(e)}")
            return None

# ============================================================================
# MESSAGE FORMATTERS
# ============================================================================

class MessageFormatter:
    """Formats messages for display."""

    @staticmethod
    def build_summary(build: Dict, budget: int, show_warnings: bool = True) -> str:
        """Format build summary."""
        if not build['cpu'] or not build['gpu']:
            error = build.get('error_message', 'Could not generate build.')
            return f"❌ Error: {error}"
        
        total = build['total_cost']
        remaining = build['remaining_budget']
        status = "✅ Under Budget!" if remaining >= 0 else "⚠️ Over Budget"
        color = "🟢" if remaining >= 0 else "🔴"
        
        summary = f"""
<b>🖥️ YOUR PC BUILD SUMMARY</b>

<b>📊 BUDGET BREAKDOWN</b>
Total Budget: ${budget:,} USD
Total Cost: ${total:,} USD
Remaining Budget: ${remaining:,} USD {color}
Budget Used: {(total/budget*100):.1f}%
{status}

<b>⭐ PERFORMANCE SCORE: {build.get('performance_score', 0):.1f}</b>

<b>⚡ POWER CONSUMPTION</b>
Total TDP: {build['total_power_consumption']}W (CPU + GPU)
Recommended PSU: {build['psu']['wattage']}W
Headroom: {build['psu']['wattage'] - build['total_power_consumption']}W

<b>🛒 SELECTED COMPONENTS</b>
• <b>CPU:</b> {build['cpu']['brand']} {build['cpu']['model']}
  Tier: {BalanceValidator.get_cpu_tier(build['cpu']).name} | {build['cpu']['cores']}C/{build['cpu']['threads']}T | {build['cpu']['boost_ghz']} GHz
  💰 ${build['cpu']['price_usd']} ({(build['cpu']['price_usd']/budget*100):.1f}%)

• <b>Motherboard:</b> {build['motherboard']['brand']} {build['motherboard']['model']}
  Max RAM Speed: {build['motherboard'].get('max_memory_speed', 'N/A')} MHz
  💰 ${build['motherboard']['price_usd']} ({(build['motherboard']['price_usd']/budget*100):.1f}%)

• <b>RAM:</b> {build['ram']['brand']} {build['ram']['model']}
  {build['ram']['capacity_gb']}GB {build['ram']['type']} @ {build['ram']['speed_mhz']} MHz
  💰 ${build['ram']['price_usd']} ({(build['ram']['price_usd']/budget*100):.1f}%)

• <b>Cooler:</b> {build['cooler']['brand']} {build['cooler']['model']}
  💰 ${build['cooler']['price_usd']}

• <b>GPU:</b> {build['gpu']['brand']} {build['gpu']['model']}
  Tier: {BalanceValidator.get_gpu_tier(build['gpu']).name} | {build['gpu']['memory_gb']}GB | PCIe Gen {build['gpu'].get('pcie_gen', '?')}
  💰 ${build['gpu']['price_usd']} ({(build['gpu']['price_usd']/budget*100):.1f}%)

• <b>Storage:</b> {build['storage_primary']['brand']} {build['storage_primary']['model']}
  {build['storage_primary']['capacity_gb']}GB | {build['storage_primary']['seq_read_mbs']} MB/s
  💰 ${build['storage_primary']['price_usd']}

• <b>Case:</b> {build['case']['brand']} {build['case']['model']}
  💰 ${build['case']['price_usd']}

• <b>PSU:</b> {build['psu']['brand']} {build['psu']['model']}
  {build['psu']['efficiency_rating']}
  💰 ${build['psu']['price_usd']}
"""
        
        if show_warnings and build.get('balance_warnings'):
            summary += f"\n<b>⚠️ BALANCE NOTES:</b>\n"
            for warning in build['balance_warnings']:
                summary += f"{warning}\n"
        
        summary += "\n✅ <b>All components are compatible!</b>"
        return summary

    @staticmethod
    def upgrade_options(component_type: str, options: List[Dict], current_build: Dict) -> str:
        """Format upgrade options for a specific component."""
        if not options:
            return f"❌ No compatible upgrades available for {component_type.upper()}"
        
        current_component = current_build[component_type]
        current_price = current_component['price_usd']
        
        message = f"""
<b>🔄 UPGRADE OPTIONS FOR {component_type.upper()}</b>

<b>Current Component:</b>
{current_component['brand']} {current_component['model']} - ${current_price}

<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
<b>AVAILABLE UPGRADES:</b>

"""
        
        for i, option in enumerate(options, 1):
            price_diff = option['price_usd'] - current_price
            
            if component_type == 'gpu':
                tier = BalanceValidator.get_gpu_tier(option)
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   Tier: {tier.name} | {option['memory_gb']}GB {option['memory_type']}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'cpu':
                tier = BalanceValidator.get_cpu_tier(option)
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   Tier: {tier.name} | {option['cores']}C/{option['threads']}T | {option['boost_ghz']} GHz
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'ram':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['capacity_gb']}GB @ {option['speed_mhz']} MHz | CAS {option['cas_latency']}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'storage_primary':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['capacity_gb']}GB | {option['seq_read_mbs']} MB/s
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'cooler':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['type']} | TDP: {option['tdp_rating']}W
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
            elif component_type == 'psu':
                message += f"""
{i}️⃣ <b>{option['brand']} {option['model']}</b>
   {option['wattage']}W | {option['efficiency_rating']}
   Price: ${option['price_usd']} (+${price_diff})
   Type: <code>upgrade {i}</code>

"""
        
        message += f"""
<b>━━━━━━━━━━━━━━━━━━━━━━━</b>
📝 <b>How to upgrade:</b> Type <code>upgrade 1</code>, <code>upgrade 2</code>, or <code>upgrade 3</code>
🔙 Type <code>back</code> to return to main options
"""
        return message

    @staticmethod
    def full_details(build: Dict, budget: int) -> str:
        """Format complete build details."""
        if not build['cpu'] or not build['gpu']:
            return "❌ Error: Incomplete build."
        
        gpu_interface = f"PCIe Gen {build['gpu'].get('pcie_gen', '?')}"
        cpu_tier = BalanceValidator.get_cpu_tier(build['cpu'])
        gpu_tier = BalanceValidator.get_gpu_tier(build['gpu'])
        
        return f"""
<b>════════════════════════════════════════</b>
<b>🖥️  COMPLETE PC BUILD CONFIGURATION</b>
<b>════════════════════════════════════════</b>

<b>📊 BUILD HEALTH</b>
Performance Score: {build.get('performance_score', 0):.1f}
CPU Tier: {cpu_tier.name}
GPU Tier: {gpu_tier.name}
Balance Status: ✅ BALANCED
Budget Usage: {(build['total_cost']/budget*100):.1f}%

<b>💰 BUDGET SUMMARY</b>
Total Budget: ${budget:,} USD
Total Cost: ${build['total_cost']:,} USD
Remaining: ${build['remaining_budget']:,} USD

<b>⚡ POWER CONSUMPTION</b>
CPU TDP: {build['cpu']['tdp']}W
GPU TDP: {build['gpu']['tdp']}W
Total System TDP: {build['total_power_consumption']}W
PSU Capacity: {build['psu']['wattage']}W
Headroom: {build['psu']['wattage'] - build['total_power_consumption']}W

<b>═══════════════════════════════════════</b>
<b>🔧 PROCESSOR (CPU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['cpu']['brand']}
Model: {build['cpu']['model']}
Tier: {cpu_tier.name}
Cores/Threads: {build['cpu']['cores']}C / {build['cpu']['threads']}T
Base Clock: {build['cpu']['base_ghz']} GHz
Boost Clock: {build['cpu']['boost_ghz']} GHz
Socket: {build['cpu']['socket']}
TDP: {build['cpu']['tdp']}W
Price: ${build['cpu']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🛠️  MOTHERBOARD</b>
<b>═══════════════════════════════════════</b>
Brand: {build['motherboard']['brand']}
Model: {build['motherboard']['model']}
Chipset: {build['motherboard']['chipset']}
Socket: {build['motherboard']['socket']}
Form Factor: {build['motherboard']['form_factor']}
Memory Type: {build['motherboard']['memory_type']}
Max Memory Speed: {build['motherboard'].get('max_memory_speed', 'N/A')} MHz
M.2 Slots: {build['motherboard']['m2_slots']}
Price: ${build['motherboard']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>💾 RAM (MEMORY)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['ram']['brand']}
Model: {build['ram']['model']}
Type: {build['ram']['type']}
Capacity: {build['ram']['capacity_gb']} GB
Speed: {build['ram']['speed_mhz']} MHz
CAS Latency: {build['ram']['cas_latency']}
Price: ${build['ram']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>❄️  CPU COOLER</b>
<b>═══════════════════════════════════════</b>
Brand: {build['cooler']['brand']}
Model: {build['cooler']['model']}
Type: {build['cooler']['type']}
TDP Rating: {build['cooler']['tdp_rating']}W
Price: ${build['cooler']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🎮 GRAPHICS CARD (GPU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['gpu']['brand']}
Model: {build['gpu']['model']}
Tier: {gpu_tier.name}
VRAM: {build['gpu']['memory_gb']} GB {build['gpu']['memory_type']}
Bus Width: {build['gpu']['bus_width']}-bit
Interface: {gpu_interface}
TDP: {build['gpu']['tdp']}W
Price: ${build['gpu']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>💿 PRIMARY STORAGE</b>
<b>═══════════════════════════════════════</b>
Brand: {build['storage_primary']['brand']}
Model: {build['storage_primary']['model']}
Capacity: {build['storage_primary']['capacity_gb']} GB
Type: {build['storage_primary']['type']}
Sequential Read: {build['storage_primary']['seq_read_mbs']} MB/s
Price: ${build['storage_primary']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🏢 PC CASE</b>
<b>═══════════════════════════════════════</b>
Brand: {build['case']['brand']}
Model: {build['case']['model']}
Form Factor: {build['case']['form_factor']}
Max GPU Length: {build['case']['max_gpu_length_mm']}mm
Price: ${build['case']['price_usd']}

<b>═══════════════════════════════════════</b>
<b>🔌 POWER SUPPLY UNIT (PSU)</b>
<b>═══════════════════════════════════════</b>
Brand: {build['psu']['brand']}
Model: {build['psu']['model']}
Wattage: {build['psu']['wattage']}W
Efficiency Rating: {build['psu']['efficiency_rating']}
Price: ${build['psu']['price_usd']}

<b>════════════════════════════════════════</b>
✨ Build is perfectly balanced and optimized! ✨
<b>════════════════════════════════════════</b>
"""

# ============================================================================
# CONVERSATION HANDLERS
# ============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Start the bot."""
    welcome = """
🖥️ Welcome to PC Build Assistant Bot! 🖥️

I'm here to help you build a PERFECTLY BALANCED PC within your budget.

Key Features:
✅ Smart GPU/CPU balancing
✅ Tier-based component matching
✅ No more weak GPUs with overkill CPUs!
✅ Upgrade individual components
✅ Full compatibility checking
✅ Performance scoring

🎮 Gaming: GPU gets 45% of budget
🎬 Content Creation: CPU gets 30% of budget

Let's get started! 💰

What's your PC build budget? (Enter amount in USD, e.g., 1500)
    """
    await update.message.reply_text(welcome)
    return BUDGET

async def get_budget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Get budget from user."""
    try:
        budget = int(update.message.text)
        
        if budget < 800:
            await update.message.reply_text(
                "❌ Budget too low. Minimum budget is $800 USD.\n\nPlease enter a valid budget:"
            )
            return BUDGET
        
        if budget > 100000:
            await update.message.reply_text(
                "❌ Budget too high. Please enter a realistic amount (max $100,000):"
            )
            return BUDGET
        
        context.user_data['budget'] = budget
        logger.info(f"User set budget: ${budget}")
        
        build_type_msg = f"""
✅ Budget set to: ${budget:,} USD

Now, choose your build type:

🎮 <b>Gaming</b>
   → GPU gets 45% of budget
   → Balanced performance focus
   → High FPS gaming priority

🎬 <b>Content Creation</b>
   → CPU gets 30% of budget
   → RAM gets 25% of budget
   → Rendering & editing focus

Type: "Gaming" or "Content Creation"
        """
        await update.message.reply_text(build_type_msg, parse_mode='HTML')
        return BUILD_TYPE
        
    except ValueError:
        await update.message.reply_text("❌ Please enter a valid number (e.g., 1500)")
        return BUDGET

async def select_build_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle build type selection."""
    user_input = update.message.text.lower().strip()
    
    if 'gaming' in user_input:
        build_type = 'gaming'
    elif 'content' in user_input or 'creation' in user_input:
        build_type = 'content_creation'
    else:
        await update.message.reply_text(
            '❌ Invalid input. Type "Gaming" or "Content Creation"'
        )
        return BUILD_TYPE
    
    context.user_data['build_type'] = build_type
    config = BUILD_CONFIGS[build_type]
    
    logger.info(f"User selected: {build_type}")
    
    await update.message.reply_text(
        f"✅ Selected: {config['description']}\n\n"
        f"🔄 Generating balanced build...\n"
        f"⏳ Analyzing GPU/CPU balance...\n"
        f"⏳ Optimizing component selection..."
    )
    
    # Generate balanced build
    build = BuildGenerator.generate(
        budget=context.user_data['budget'],
        build_type=build_type,
        allocations=config['budget_allocation']
    )
    
    if not build.get('cpu') or not build.get('gpu'):
        error = build.get('error_message', 'Could not generate build.')
        await update.message.reply_text(
            f"❌ {error}\n\n"
            f"Minimum budget: $1,200 USD\n\n"
            f"Type /start to try again."
        )
        logger.warning(f"Build failed: {error}")
        return -1
    
    build['build_type'] = build_type
    context.user_data['build'] = build
    formatter = MessageFormatter()
    
    await update.message.reply_text(
        formatter.build_summary(build, context.user_data['budget']),
        parse_mode='HTML'
    )
    
    await update.message.reply_text(
        """
✨ <b>BUILD COMPLETE!</b>

<b>🔄 UPGRADE OPTIONS:</b>
What would you like to do?

Type a command:
• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply

Or:
• <code>details</code> - View full specifications
• <code>start</code> - Create a new build
        """,
        parse_mode='HTML'
    )
    return UPGRADE_MENU

async def upgrade_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upgrade menu selection."""
    user_input = update.message.text.lower().strip()
    
    build = context.user_data.get('build')
    budget = context.user_data.get('budget')
    
    if not build or not budget:
        await update.message.reply_text("❌ No build found. Type /start to create one.")
        return -1
    
    formatter = MessageFormatter()
    upgrade_engine = UpgradeEngine()
    
    if user_input.startswith('upgrade'):
        parts = user_input.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Usage: Type 'upgrade gpu', 'upgrade cpu', etc.")
            return UPGRADE_MENU
        
        component_type = parts[1]
        
        component_map = {
            'gpu': 'gpu',
            'cpu': 'cpu',
            'ram': 'ram',
            'cooler': 'cooler',
            'storage': 'storage_primary',
            'psu': 'psu'
        }
        
        if component_type not in component_map:
            await update.message.reply_text(
                f"❌ Invalid component. Valid options: {', '.join(component_map.keys())}"
            )
            return UPGRADE_MENU
        
        component_key = component_map[component_type]
        
        # Debug: Show current component info
        current = build[component_key]
        logger.info(f"Checking upgrades for {component_type}: current={current.get('model')} (${current['price_usd']})")
        logger.info(f"Budget remaining: ${budget - (build['total_cost'] - current['price_usd'])}")
        
        # Get upgrade options
        options = upgrade_engine.get_compatible_upgrades(build, component_key, budget)
        
        if not options:
            remaining = budget - (build['total_cost'] - current['price_usd'])
            await update.message.reply_text(
                f"❌ No compatible upgrades available for {component_type.upper()}\n\n"
                f"Current: {current['brand']} {current['model']} (${current['price_usd']})\n"
                f"Remaining budget: ${remaining}\n\n"
                f"Reason: All better options exceed your remaining budget or don't exist."
            )
            return UPGRADE_MENU
        
        # Store options in context for next step
        context.user_data['upgrade_options'] = options
        context.user_data['upgrade_component'] = component_key
        
        # Show upgrade options
        upgrade_msg = formatter.upgrade_options(component_key, options, build)
        await update.message.reply_text(upgrade_msg, parse_mode='HTML')
        return UPGRADE_SELECTION
    
    elif 'detail' in user_input:
        detailed_msg = formatter.full_details(build, budget)
        
        if len(detailed_msg) > 4096:
            parts = [detailed_msg[i:i+4096] for i in range(0, len(detailed_msg), 4096)]
            for part in parts:
                await update.message.reply_text(part, parse_mode='HTML')
        else:
            await update.message.reply_text(detailed_msg, parse_mode='HTML')
        
        await update.message.reply_text(
            "✨ Type an upgrade command or /start for a new build.",
            parse_mode='HTML'
        )
        return UPGRADE_MENU
    
    elif 'start' in user_input or 'new' in user_input:
        return await start(update, context)
    
    else:
        await update.message.reply_text(
            """
❌ Invalid command. Type one of:
• <code>upgrade gpu</code>
• <code>upgrade cpu</code>
• <code>upgrade ram</code>
• <code>upgrade cooler</code>
• <code>upgrade storage</code>
• <code>upgrade psu</code>
• <code>details</code>
        """,
            parse_mode='HTML'
        )
        return UPGRADE_MENU

async def upgrade_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Handle upgrade selection."""
    user_input = update.message.text.lower().strip()
    
    build = context.user_data.get('build')
    budget = context.user_data.get('budget')
    options = context.user_data.get('upgrade_options', [])
    component_key = context.user_data.get('upgrade_component')
    
    if not build or not budget:
        await update.message.reply_text("❌ No build found. Type /start to create one.")
        return -1
    
    formatter = MessageFormatter()
    upgrade_engine = UpgradeEngine()
    
    if user_input.startswith('upgrade'):
        parts = user_input.split()
        if len(parts) < 2:
            await update.message.reply_text("❌ Usage: Type 'upgrade 1', 'upgrade 2', or 'upgrade 3'")
            return UPGRADE_SELECTION
        
        try:
            option_index = int(parts[1]) - 1
            if option_index < 0 or option_index >= len(options):
                await update.message.reply_text(
                    f"❌ Invalid selection. Choose 1-{len(options)}"
                )
                return UPGRADE_SELECTION
            
            selected_option = options[option_index]
            
            # Apply upgrade
            upgraded_build = upgrade_engine.apply_upgrade(
                build,
                component_key,
                selected_option,
                budget
            )
            
            if not upgraded_build:
                await update.message.reply_text(
                    "❌ Upgrade exceeds budget. Try a cheaper option."
                )
                return UPGRADE_SELECTION
            
            context.user_data['build'] = upgraded_build
            
            await update.message.reply_text("✅ Upgrade applied successfully!")
            await update.message.reply_text(
                formatter.build_summary(upgraded_build, budget),
                parse_mode='HTML'
            )
            
            await update.message.reply_text(
                """
<b>🔄 UPGRADE OPTIONS:</b>
What would you like to do next?

• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply
• <code>details</code> - View full specifications
• <code>start</code> - Create a new build
                """,
                parse_mode='HTML'
            )
            return UPGRADE_MENU
        
        except (ValueError, IndexError):
            await update.message.reply_text(
                f"❌ Invalid input. Use 'upgrade 1', 'upgrade 2', or 'upgrade 3'"
            )
            return UPGRADE_SELECTION
    
    elif 'back' in user_input:
        await update.message.reply_text("🔙 Returning to upgrade menu...")
        await update.message.reply_text(
            """
<b>🔄 UPGRADE OPTIONS:</b>

• <code>upgrade gpu</code> - Upgrade Graphics Card
• <code>upgrade cpu</code> - Upgrade Processor
• <code>upgrade ram</code> - Upgrade Memory
• <code>upgrade cooler</code> - Upgrade CPU Cooler
• <code>upgrade storage</code> - Upgrade Storage
• <code>upgrade psu</code> - Upgrade Power Supply
• <code>details</code> - View full specifications
            """,
            parse_mode='HTML'
        )
        return UPGRADE_MENU
    
    else:
        await update.message.reply_text(
            f"❌ Invalid input. Type 'upgrade 1', 'upgrade 2', 'upgrade 3', or 'back'"
        )
        return UPGRADE_SELECTION

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show help."""
    help_text = """
<b>🖥️ PC BUILD ASSISTANT - HELP</b>

<b>Commands:</b>
/start - Start building a PC
/help - Show this message
/about - About the bot

<b>How to Use:</b>
1. Type /start
2. Enter your total budget
3. Choose build type (Gaming or Content Creation)
4. Review the generated build
5. Upgrade components if desired
6. Type "details" for full specifications

<b>Build Types:</b>
🎮 <b>Gaming:</b> GPU-focused, 45% budget
🎬 <b>Content Creation:</b> CPU+RAM focused, 30%+25%

<b>What's New:</b>
✨ Smart GPU/CPU balancing
✨ Tier-based component matching
✨ Individual component upgrades
✨ Full compatibility checking

Minimum Budget: $800 USD
    """
    await update.message.reply_text(help_text, parse_mode='HTML')

async def about_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show about."""
    about_text = """
<b>About PC Build Assistant Bot</b>

Version 5.0 - Improved Upgrade System

<b>🎯 Core Features:</b>
✅ GPU/CPU balance enforcement
✅ Tier-based component matching
✅ Performance scoring system
✅ Smart budget allocation
✅ Individual component upgrades
✅ Full compatibility checking
✅ Power consumption analysis

<b>🆕 New in 5.0:</b>
🔹 Fixed GPU upgrade path (no more skipping)
🔹 Proper intermediate options (RTX 5050 → 5060 → 5070...)
🔹 Improved upgrade filtering logic
🔹 Better logging and debugging
🔹 All upgrade paths now complete

<b>📊 How It Works:</b>
1. Analyzes your budget and use case
2. Allocates budget correctly
3. Selects balanced components by tier
4. Scores overall performance
5. Shows logical upgrade progression
6. Validates compatibility at each step

Built with ❤️ for balanced PC builds
    """
    await update.message.reply_text(about_text, parse_mode='HTML')

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Cancel conversation."""
    await update.message.reply_text("Cancelled. Type /start to begin again.")
    return -1

# ============================================================================
# MAIN
# ============================================================================

def main() -> None:
    """Start the bot."""
    if not BOT_TOKEN:
        logger.error("❌ BOT_TOKEN not found in .env")
        print("❌ BOT_TOKEN not found! Set it in .env file")
        return
    
    if not load_database():
        logger.error("❌ Failed to load database")
        return
    
    application = Application.builder().token(BOT_TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            BUDGET: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_budget)],
            BUILD_TYPE: [MessageHandler(filters.TEXT & ~filters.COMMAND, select_build_type)],
            UPGRADE_MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, upgrade_menu)],
            UPGRADE_SELECTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, upgrade_selection)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )
    
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CommandHandler('about', about_command))
    
    logger.info("🤖 Balanced Build Bot ready!")
    print("🤖 Bot started and listening...")
    application.run_polling()

if __name__ == '__main__':
    main()