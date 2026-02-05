import { Visa } from "@/api/visas";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/UI/card";
import { Button } from "@/components/UI/button";
import { motion } from "framer-motion";
import { Link } from "react-router-dom";

/**
 * Полностью переработанная карточка визы
 * - Кнопка всегда закреплена внизу
 * - Высота карточек выровнена
 * - Увеличены отступы
 * - Описание ограничено и красиво переносится
 * - Карточки адаптивные
 */

export const VisaCard = ({ visa }: { visa: Visa }) => {
  return (
    <motion.div
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.2 }}
      className="h-full"
    >
      <Card className="h-full flex flex-col rounded-2xl shadow-sm hover:shadow-md transition-shadow p-2">
        <CardHeader className="pb-2">
          <CardTitle className="text-lg font-semibold leading-tight">
            {visa.name}
          </CardTitle>
        </CardHeader>

        <CardContent className="flex flex-col flex-grow justify-between">
          {/* Описание */}
          <p className="text-sm text-slate-600 flex-grow mb-4 line-clamp-4 break-words">
            {visa.description}
          </p>

          {/* Закрепленная кнопка */}
          <div className="mt-auto pt-3">
            <Link to={`/visas/${visa.code}`} className="w-full block">
              <Button size="sm" className="w-full rounded-xl">
                Подробнее
              </Button>
            </Link>
          </div>
        </CardContent>
      </Card>
    </motion.div>
  );
};