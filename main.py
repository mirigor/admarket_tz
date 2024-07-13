# Вводные данные

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum, F, Value, DecimalField, Case, When
from django.db.models.functions import Coalesce


class Building(models.Model):
    name = models.CharField()

    class Meta:
        verbose_name = 'Объект строительства'


class Section(models.Model):
    building = models.ForeignKey(Building, on_delete=models.PROTECT)
    parent = models.ForeignKey('self', on_delete=models.PROTECT, verbose_name='Родительская секция',
                               blank=False, null=True)

    class Meta:
        verbose_name = 'Секция сметы'

    def save(self, force_insert=False, force_update=False, using=None, update_fields=None):
        if not self.id and self.parent and getattr(self.parent, 'parent', None):
            raise ValidationError('Максимальный уровень вложенности 2')
        super().save(force_insert, force_update, using, update_fields)


class Expenditure(models.Model):
    class Types:
        WORK = 'work'
        MATERIAL = 'material'
        choices = (
            (WORK, 'Работа'),
            (MATERIAL, 'Материал'),
        )

    section = models.ForeignKey(Section, on_delete=models.PROTECT,
                                help_text='Расценка может принадлежать только той секции, у которой указан parent')
    name = models.CharField(verbose_name='Название расценки')
    type = models.CharField(verbose_name='Тип расценки', choices=Types.choices, max_length=8)
    count = models.DecimalField(verbose_name='Кол-во', max_digits=20, decimal_places=8)
    price = models.DecimalField(verbose_name='Цена за единицу', max_digits=20, decimal_places=2)

    class Meta:
        verbose_name = 'Расценка сметы'


# Задание 1

# Написать тело функции, которая для каждого конкретного объекта строительства будет возвращать список
# только родительских секций. У каждой родительской секции необходимо посчитать бюджет (стоимость всех расценок внутри).

def get_parent_sections(building_id: int) -> list[Section]:
    # Выбираем только родительские разделы. Аннотируем каждый родительский раздел суммой расходов всех его дочерних разделов
    return list(
        Section.objects.filter(building_id=building_id, parent=None).annotate(
            total_budget=Coalesce(
                Sum(F('section_set__expenditure__count') * F('section_set__expenditure__price')),
                Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            )
        )
    )


# Задание 2

# Написать функцию, которая вернёт список объектов строительства, у каждого объекта строительства необходимо посчитать
# стоимость всех работ и стоимость всех материалов.

def get_buildings() -> list[dict]:
    """
    Ожидаемый результат функции:
    [
        {
            'id': 1,
            'works_amount': 100.00,
            'materials_amount': 200.00,
        },
        {
            'id': 2,
            'works_amount': 100.00,
            'materials_amount': 0.00,
        },
    ]
    """
    buildings = Building.objects.annotate(
        works_amount=Sum(
            Case(
                When(section__expenditure__type=Expenditure.Types.WORK,
                     then=F('section__expenditure__count') * F('section__expenditure__price')),
                default=Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            )
        ),
        materials_amount=Sum(
            Case(
                When(section__expenditure__type=Expenditure.Types.MATERIAL,
                     then=F('section__expenditure__count') * F('section__expenditure__price')),
                default=Value(Decimal('0.00')),
                output_field=DecimalField(max_digits=20, decimal_places=2)
            )
        )
    )

    return [
        {
            'id': building.id,
            'works_amount': building.works_amount,
            'materials_amount': building.materials_amount
        }
        for building in buildings
    ]

# Задание 3

# Пользователь хочет применить скидку для секции на стоимость всех расценок внутри. Написать функцию, которая обновит
# поле price у всех расценок внутри секции с учётом этой скидки.


def update_with_discount(section_id: int, discount: Decimal):
    """
    @param section_id: ID секции, для которой применяется скидка.
    @param discount: Размер скидки в процентах от Decimal(0) до Decimal(100)
    """

    # Проверка на валидность входных данных
    if not (Decimal(0) <= discount <= Decimal(100)):
        raise ValueError("Discount must be between 0 and 100 percent.")

    # Вычисление коэффициента скидки
    discount_factor = Decimal('1.00') - (discount / Decimal('100.00'))

    # Обновление цен расценок внутри секции
    Expenditure.objects.filter(section_id=section_id).update(
        price=F('price') * discount_factor
    )
